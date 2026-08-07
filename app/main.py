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
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from . import guardrails, llm, memory
from .assess import assess
from .models import CaseRecord, Correction, RiskFinding, Severity
from .report import render_cases, render_index, render_playbook, render_report, render_review

llm.require()  # no LLM configured -> fail here, at startup, with a clear message

app = FastAPI(title="Self-Learning Underwriting POC")

_SAMPLE_PATH = Path(__file__).parent.parent / "sample_data" / "sample_application.md"
_INDEX_HTML = render_index(
    sample=_SAMPLE_PATH.read_text(encoding="utf-8") if _SAMPLE_PATH.exists() else ""
)

# draft_id -> {"draft": ..., "result": ..., "engine": ..., "raw_text": ...}
DRAFTS: dict = {}


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _read_raw(text: Optional[str], file: Optional[UploadFile]) -> str:
    if file is not None and file.filename:
        return file.file.read().decode("utf-8", errors="replace")
    if text:
        return text
    raise HTTPException(status_code=400, detail="Provide raw text or upload a file.")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(_INDEX_HTML)


@app.post("/assess", response_class=HTMLResponse)
async def assess_route(
    raw_text: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = None,
) -> HTMLResponse:
    raw = _read_raw(raw_text, file)
    draft, engine = assess(raw)
    result = guardrails.apply(draft, raw)
    draft_id = uuid.uuid4().hex[:12]
    DRAFTS[draft_id] = {"draft": draft, "result": result, "engine": engine, "raw_text": raw}
    return HTMLResponse(render_review(draft_id, draft, result, engine, _now()))


@app.post("/approve", response_class=HTMLResponse)
async def approve(request: Request) -> HTMLResponse:
    form = await request.form()
    draft_id = form.get("draft_id", "")
    pending = DRAFTS.pop(draft_id, None)
    if pending is None:
        raise HTTPException(status_code=404, detail="Draft not found (already approved, or server restarted).")

    draft, result = pending["draft"], pending["result"]
    approved, corrections = _apply_review(form, result.findings)

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
    learning_note = memory.reflect(case)
    return HTMLResponse(render_report(case, pending["engine"], _now(), learning_note))


def _apply_review(form, draft_findings) -> tuple:
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
        approved.append(RiskFinding(
            factor_name=new_name,
            section=(form.get("new_section") or "General").strip() or "General",
            severity=severity,
            suggested_points=max(0, min(points, guardrails.POINT_CAPS[severity])),
            evidence_quote="",
            reasoning=(form.get("new_reasoning") or "Added by reviewer.").strip(),
            confidence=1.0,
        ))
        corrections.append(Correction(type="added", factor_name=new_name, detail="added by reviewer"))

    return approved, corrections


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
