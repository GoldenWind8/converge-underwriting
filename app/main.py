"""
FastAPI app — plumbing only; the interesting logic lives in assess.py,
guardrails.py and memory.py.

The loop:
  POST /assess    raw text -> draft findings -> guardrails -> editable review page
  POST /approve   reviewer's edits -> CaseRecord stored -> reflection updates the
                  playbook -> final report
  GET  /cases     browse memory;  GET /cases/{id} re-renders a stored report
  GET  /playbook  the current playbook

Drafts awaiting review are held in memory (DRAFTS) — fine for a single-process POC.
"""

from __future__ import annotations

import datetime as _dt
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import guardrails, llm, memory
from .assess import assess
from .models import CaseRecord, Correction, RiskFinding, Severity
from .report import (render_cases, render_error, render_index, render_playbook,
                     render_report, render_review)

llm.require()  # no LLM configured -> fail here, at startup, with a clear message

app = FastAPI(title="Converge Underwriting POC")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

_SAMPLE_PATH = Path(__file__).parent.parent / "sample_data" / "sample_application.md"
_SAMPLE = _SAMPLE_PATH.read_text(encoding="utf-8") if _SAMPLE_PATH.exists() else ""
_MAX_INPUT_BYTES = 250_000

# draft_id -> {"draft": ..., "result": ..., "engine": ..., "raw_text": ...}
DRAFTS: dict = {}
PENDING_LEARNING: dict[str, memory.LearningProposal] = {}


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _read_raw(text: Optional[str], file: Optional[UploadFile]) -> str:
    if file is not None and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".txt", ".md", ".csv"}:
            raise HTTPException(status_code=400, detail="Upload a .txt, .md, or .csv document.")
        content = file.file.read(_MAX_INPUT_BYTES + 1)
        if len(content) > _MAX_INPUT_BYTES:
            raise HTTPException(status_code=413, detail="Document is too large (250 KB maximum).")
        return content.decode("utf-8", errors="replace")
    if text:
        if len(text.encode("utf-8")) > _MAX_INPUT_BYTES:
            raise HTTPException(status_code=413, detail="Document is too large (250 KB maximum).")
        return text
    raise HTTPException(status_code=400, detail="Provide raw text or upload a file.")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    cases = memory.all_cases()
    rules = set(re.findall(r"\bPB-\d+\b", memory.load_playbook(), flags=re.IGNORECASE))
    return HTMLResponse(render_index(_SAMPLE, len(cases), len(rules)))


@app.post("/assess", response_class=HTMLResponse)
async def assess_route(
    raw_text: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = None,
) -> HTMLResponse:
    raw = _read_raw(raw_text, file)
    try:
        draft, engine = assess(raw)
        result = guardrails.apply(draft, raw)
    except Exception as exc:  # provider/schema failures should be recoverable in the POC UI
        return HTMLResponse(
            render_error("Assessment could not be completed", str(exc)), status_code=502
        )
    draft_id = uuid.uuid4().hex[:12]
    DRAFTS[draft_id] = {"draft": draft, "result": result, "engine": engine, "raw_text": raw}
    return HTMLResponse(render_review(draft_id, draft, result, engine, _now(), raw))


@app.get("/review/{draft_id}", response_class=HTMLResponse)
def resume_review(draft_id: str) -> HTMLResponse:
    pending = DRAFTS.get(draft_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Draft not found (it may have expired or been approved).")
    return HTMLResponse(render_review(
        draft_id, pending["draft"], pending["result"], pending["engine"],
        _now(), pending["raw_text"],
    ))


@app.post("/approve", response_class=HTMLResponse)
async def approve(request: Request) -> HTMLResponse:
    form = await request.form()
    draft_id = form.get("draft_id", "")
    pending = DRAFTS.get(draft_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Draft not found (already approved, or server restarted).")

    draft, result = pending["draft"], pending["result"]
    try:
        approved, corrections = _apply_review(form, result.findings, pending["raw_text"])
    except HTTPException as exc:
        return HTMLResponse(
            render_error("Review needs attention", str(exc.detail), f"/review/{draft_id}"),
            status_code=exc.status_code,
        )

    score = sum(f.suggested_points for f in approved)
    band = guardrails.band_for_score(score)
    case = CaseRecord(
        case_id=memory.next_case_id(),
        created_at=_dt.datetime.now().isoformat(timespec="seconds"),
        source="assessment",
        client_profile=draft.client_profile,
        summary=draft.client_profile.summary,
        draft_findings=result.findings,
        approved_findings=approved,
        corrections=corrections,
        final_score=score,
        final_band=band,
    )
    memory.store(case)
    DRAFTS.pop(draft_id, None)
    proposal = None
    learning_note = None
    try:
        proposal = memory.propose_reflection(case)
        if proposal is not None:
            PENDING_LEARNING[case.case_id] = proposal
    except Exception:
        learning_note = "Case approved. The learning proposal is temporarily unavailable and can be retried later."
    return HTMLResponse(render_report(
        case, pending["engine"], _now(), learning_note, proposal
    ))


def _apply_review(form, draft_findings, raw_text: str = "") -> tuple:
    """Turn the review form back into approved findings + a corrections diff."""
    approved, corrections = [], []

    for i, f in enumerate(draft_findings):
        if form.get(f"keep_{i}") is None:
            corrections.append(Correction(type="removed", factor_name=f.factor_name))
            continue
        severity = Severity(form.get(f"severity_{i}", f.severity.value))
        try:
            points = int(form.get(f"points_{i}", f.suggested_points))
        except ValueError:
            points = f.suggested_points
        points = max(0, min(points, guardrails.POINT_CAPS[severity]))
        if severity != f.severity:
            corrections.append(Correction(
                type="severity_changed", factor_name=f.factor_name,
                detail=f"{f.severity.value} -> {severity.value}",
            ))
        if points != f.suggested_points and severity == f.severity:
            corrections.append(Correction(
                type="points_changed", factor_name=f.factor_name,
                detail=f"{f.suggested_points} -> {points}",
            ))
        approved.append(f.model_copy(update={"severity": severity, "suggested_points": points}))

    new_name = (form.get("new_factor_name") or "").strip().lower().replace(" ", "_")
    if new_name:
        severity = Severity(form.get("new_severity", "medium"))
        try:
            points = int(form.get("new_points", 0))
        except ValueError:
            points = 0
        evidence = (form.get("new_evidence_quote") or "").strip()
        if not guardrails.evidence_is_present(evidence, raw_text):
            raise HTTPException(
                status_code=400,
                detail="A reviewer-added finding needs an evidence quote copied from the source document.",
            )
        approved.append(RiskFinding(
            factor_name=new_name,
            section=(form.get("new_section") or "General").strip() or "General",
            severity=severity,
            suggested_points=max(0, min(points, guardrails.POINT_CAPS[severity])),
            evidence_quote=evidence,
            reasoning=(form.get("new_reasoning") or "Added by reviewer.").strip(),
            confidence=1.0,
        ))
        corrections.append(Correction(type="added", factor_name=new_name, detail="added by reviewer"))

    return approved, corrections


@app.post("/learning/{case_id}", response_class=HTMLResponse)
async def decide_learning(case_id: str, request: Request) -> HTMLResponse:
    case = memory.get_case(case_id)
    proposal = PENDING_LEARNING.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    if proposal is None:
        return HTMLResponse(render_report(case, "stored", _now(), "No pending learning proposal."))

    form = await request.form()
    action = form.get("action", "skip")
    if action == "accept":
        edited = (form.get("proposed_playbook") or "").strip()
        if not edited:
            raise HTTPException(status_code=400, detail="The playbook update cannot be empty.")
        memory.save_playbook(edited + "\n")
        note = proposal.change_note + (" Edited and approved by the underwriter." if edited != proposal.proposed_playbook.strip() else " Approved by the underwriter.")
    else:
        note = "Playbook update skipped. The approved case remains available as a precedent."
    PENDING_LEARNING.pop(case_id, None)
    return HTMLResponse(render_report(case, "stored", _now(), note))


@app.get("/cases", response_class=HTMLResponse)
def cases() -> HTMLResponse:
    return HTMLResponse(render_cases(memory.all_cases()))


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail(case_id: str) -> HTMLResponse:
    case = memory.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return HTMLResponse(render_report(case, "stored", _now()))


@app.get("/playbook", response_class=HTMLResponse)
def playbook() -> HTMLResponse:
    return HTMLResponse(render_playbook(memory.load_playbook()))


@app.post("/demo/reset")
def reset_demo() -> RedirectResponse:
    memory.reset_demo_data()
    DRAFTS.clear()
    PENDING_LEARNING.clear()
    return RedirectResponse(url="/", status_code=303)
