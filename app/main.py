"""
FastAPI app — plumbing only; the interesting logic lives in needs.py,
assess.py, guardrails.py and memory.py.

The loop (three human gates):
  POST /assess          raw text -> profile + needs determination -> needs table
  POST /needs/{id}      GATE 1: the underwriter's confirmed table -> one
                        assessment call per required section -> guardrails ->
                        editable review page
  POST /approve         GATE 2: reviewer's edits -> CaseRecord stored ->
                        reflection proposes a playbook update
  POST /learning/{id}   GATE 3: accept / edit / skip the playbook update
  GET  /cases           browse memory;  GET /cases/{id} re-renders a stored report
  GET  /playbook        the current playbook

Drafts awaiting a gate are held in memory (PENDING_NEEDS, DRAFTS) — fine for a
single-process POC.
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
from .assess import assess_profile, assess_sections
from .models import (CaseRecord, Correction, Requirement, RiskFinding,
                     SectionNeed, Severity)
from .needs import determine_needs
from .report import (render_cases, render_error, render_index, render_needs,
                     render_playbook, render_report, render_review)
from .sections import MotorSubType, SectionId, section

llm.require()  # no LLM configured -> fail here, at startup, with a clear message

app = FastAPI(title="Converge Underwriting POC")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

_SAMPLE_PATH = Path(__file__).parent.parent / "sample_data" / "sample_application.md"
_SAMPLE = _SAMPLE_PATH.read_text(encoding="utf-8") if _SAMPLE_PATH.exists() else ""
_MAX_INPUT_BYTES = 250_000

# needs_id -> {"determination": ..., "profile": ..., "engine": ..., "raw_text": ...}
PENDING_NEEDS: dict = {}
# draft_id -> {"draft": ..., "result": ..., "engine": ..., "raw_text": ..., "needs": ..., "usage": ...}
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
    llm.reset_usage()
    try:
        profile = assess_profile(raw)
        determination = determine_needs(raw)
    except Exception as exc:  # provider/schema failures should be recoverable in the POC UI
        return HTMLResponse(
            render_error("Needs determination could not be completed", str(exc)), status_code=502
        )
    needs_id = uuid.uuid4().hex[:12]
    PENDING_NEEDS[needs_id] = {
        "determination": determination, "profile": profile,
        "engine": llm.provider(), "raw_text": raw,
    }
    return HTMLResponse(render_needs(needs_id, determination, profile, llm.provider(), _now()))


@app.get("/needs/{needs_id}", response_class=HTMLResponse)
def resume_needs(needs_id: str) -> HTMLResponse:
    pending = PENDING_NEEDS.get(needs_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Needs determination not found (it may have expired).")
    return HTMLResponse(render_needs(
        needs_id, pending["determination"], pending["profile"], pending["engine"], _now(),
    ))


@app.post("/needs/{needs_id}", response_class=HTMLResponse)
async def confirm_needs(needs_id: str, request: Request) -> HTMLResponse:
    """Human gate 1: the underwriter's confirmed table drives the assessment."""
    pending = PENDING_NEEDS.get(needs_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Needs determination not found (it may have expired).")
    form = await request.form()

    confirmed: list[SectionNeed] = []
    for need in pending["determination"].needs:
        raw_req = form.get(f"requirement_{need.section.value}", need.requirement.value)
        try:
            requirement = Requirement(raw_req)
        except ValueError:
            requirement = need.requirement
        update: dict = {"requirement": requirement}
        if need.section == SectionId.motor:
            raw_sub = (form.get("motor_sub_type") or "").strip()
            update["motor_sub_type"] = MotorSubType(raw_sub) if raw_sub else need.motor_sub_type
        confirmed.append(need.model_copy(update=update))

    if not any(n.requirement == Requirement.required for n in confirmed):
        return HTMLResponse(
            render_error("No sections marked required",
                         "Mark at least one cover section as required before assessing.",
                         f"/needs/{needs_id}"),
            status_code=400,
        )

    try:
        draft, engine = assess_sections(pending["raw_text"], pending["profile"], confirmed)
        result = guardrails.apply(draft, pending["raw_text"])
    except Exception as exc:
        return HTMLResponse(
            render_error("Assessment could not be completed", str(exc), f"/needs/{needs_id}"),
            status_code=502,
        )
    draft_id = uuid.uuid4().hex[:12]
    DRAFTS[draft_id] = {
        "draft": draft, "result": result, "engine": engine,
        "raw_text": pending["raw_text"], "needs": confirmed,
        "usage": llm.usage_summary(),
    }
    PENDING_NEEDS.pop(needs_id, None)
    return HTMLResponse(render_review(
        draft_id, draft, result, engine, _now(), pending["raw_text"],
        confirmed, DRAFTS[draft_id]["usage"],
    ))


@app.get("/review/{draft_id}", response_class=HTMLResponse)
def resume_review(draft_id: str) -> HTMLResponse:
    pending = DRAFTS.get(draft_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Draft not found (it may have expired or been approved).")
    return HTMLResponse(render_review(
        draft_id, pending["draft"], pending["result"], pending["engine"],
        _now(), pending["raw_text"], pending["needs"], pending.get("usage"),
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

    approved.sort(key=lambda f: (section(f.section).number,
                                 -guardrails.SEVERITY_ORDER[f.severity]))
    case = CaseRecord(
        case_id=memory.next_case_id(),
        created_at=_dt.datetime.now().isoformat(timespec="seconds"),
        source="assessment",
        client_profile=draft.client_profile,
        summary=draft.client_profile.summary,
        needs=pending["needs"],
        draft_findings=result.findings,
        approved_findings=approved,
        corrections=corrections,
        final_band=guardrails.band_for_findings(approved),
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
    """Turn the review form back into approved findings + a corrections diff.
    Every correction can carry the reviewer's own 'why' note, remembered verbatim."""
    approved, corrections = [], []

    for i, f in enumerate(draft_findings):
        note = (form.get(f"note_{i}") or "").strip()
        if form.get(f"keep_{i}") is None:
            corrections.append(Correction(type="removed", factor_name=f.factor_name, note=note))
            continue
        severity = Severity(form.get(f"severity_{i}", f.severity.value))
        if severity != f.severity:
            corrections.append(Correction(
                type="severity_changed", factor_name=f.factor_name,
                detail=f"{f.severity.value} -> {severity.value}", note=note,
            ))
        approved.append(f.model_copy(update={"severity": severity}))

    new_name = (form.get("new_factor_name") or "").strip().lower().replace(" ", "_")
    if new_name:
        severity = Severity(form.get("new_severity", "medium"))
        evidence = (form.get("new_evidence_quote") or "").strip()
        if not guardrails.evidence_is_present(evidence, raw_text):
            raise HTTPException(
                status_code=400,
                detail="A reviewer-added finding needs a substantial evidence quote copied "
                       "from the source document (a word like 'Yes' is not evidence).",
            )
        try:
            new_section = SectionId(form.get("new_section", ""))
        except ValueError:
            raise HTTPException(status_code=400, detail="Pick the cover section for the added finding.")
        note = (form.get("new_note") or "").strip()
        approved.append(RiskFinding(
            factor_name=new_name,
            section=new_section,
            severity=severity,
            evidence_quote=evidence,
            reasoning=(form.get("new_reasoning") or "Added by reviewer.").strip(),
            confidence=1.0,
        ))
        corrections.append(Correction(type="added", factor_name=new_name,
                                      detail="added by reviewer", note=note))

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


@app.post("/cases/{case_id}/confirm")
def confirm_ingested_case(case_id: str) -> RedirectResponse:
    """Human confirmation of a provisional (chat-ingested) case — §7.3 gate."""
    if memory.confirm_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return RedirectResponse(url="/cases", status_code=303)


@app.get("/playbook", response_class=HTMLResponse)
def playbook() -> HTMLResponse:
    return HTMLResponse(render_playbook(memory.load_playbook()))


@app.post("/demo/reset")
def reset_demo() -> RedirectResponse:
    memory.reset_demo_data()
    PENDING_NEEDS.clear()
    DRAFTS.clear()
    PENDING_LEARNING.clear()
    return RedirectResponse(url="/", status_code=303)
