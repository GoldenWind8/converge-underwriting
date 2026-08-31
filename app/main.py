"""
FastAPI app — plumbing only; the interesting logic lives in needs.py,
assess.py, guardrails.py and memory.py.

The loop (four human gates):
  POST /assess          raw text -> profile + needs determination + stated
                        sums insured -> needs table
  POST /needs/{id}      GATE 1: the underwriter's confirmed table (sections +
                        sums insured) -> one assessment call per required
                        section -> guardrails -> editable review page
  POST /approve         GATE 2: reviewer's edits -> CaseRecord stored with a
                        deterministic pricing draft -> Price gate
  POST /cases/{id}/pricing  GATE 3: loadings confirmed/overridden -> pricing
                        saved on the case -> report + learning proposal
  POST /learning/{id}   GATE 4: accept / edit / skip the playbook update
  GET  /cases           browse memory;  GET /cases/{id} re-renders a stored report
  GET  /cases/{id}/pdf  client-facing PDF copy of a stored case (HTML -> xhtml2pdf)
  GET  /playbook        the current playbook
  GET/POST /rates       base rates + band loadings config (config/*.json)

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
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import guardrails, llm, memory, pricing
from .assess import assess_profile, assess_sections
from .models import (CaseRecord, Correction, Requirement, RiskFinding,
                     SectionNeed, Severity, SumInsured)
from .needs import determine_needs
from .pdf import case_pdf, pdf_filename
from .report import (render_cases, render_error, render_index, render_needs,
                     render_playbook, render_pricing, render_rates,
                     render_report, render_review)
from .sections import MotorSubType, SectionId, section
from .sums import extract_sums

llm.require()  # no LLM configured -> fail here, at startup, with a clear message

app = FastAPI(title="Converge Underwriting POC")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

_SAMPLE_PATH = Path(__file__).parent.parent / "sample_data" / "sample_application.md"
_SAMPLE = _SAMPLE_PATH.read_text(encoding="utf-8") if _SAMPLE_PATH.exists() else ""
_MAX_INPUT_BYTES = 250_000

# needs_id -> {"determination": ..., "profile": ..., "sums": ..., "engine": ..., "raw_text": ...}
PENDING_NEEDS: dict = {}
# draft_id -> {"draft": ..., "result": ..., "engine": ..., "raw_text": ..., "needs": ..., "sums": ..., "usage": ...}
DRAFTS: dict = {}
PENDING_LEARNING: dict[str, memory.LearningProposal] = {}
LEARNING_NOTES: dict[str, str] = {}  # case_id -> note when the proposal failed


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


def _parse_amount(raw: Optional[str]) -> Optional[int]:
    """'R30 000 000' / '30,000,000' / '30000000' -> 30000000; blank/junk -> None."""
    digits = re.sub(r"[^\d]", "", raw or "")
    return int(digits) if digits else None


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
        sums = extract_sums(raw)
    except Exception as exc:  # provider/schema failures should be recoverable in the POC UI
        return HTMLResponse(
            render_error("Needs determination could not be completed", str(exc)), status_code=502
        )
    needs_id = uuid.uuid4().hex[:12]
    PENDING_NEEDS[needs_id] = {
        "determination": determination, "profile": profile, "sums": sums,
        "engine": llm.provider(), "raw_text": raw,
    }
    return HTMLResponse(render_needs(needs_id, determination, profile, llm.provider(), _now(), sums))


@app.get("/needs/{needs_id}", response_class=HTMLResponse)
def resume_needs(needs_id: str) -> HTMLResponse:
    pending = PENDING_NEEDS.get(needs_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Needs determination not found (it may have expired).")
    return HTMLResponse(render_needs(
        needs_id, pending["determination"], pending["profile"], pending["engine"], _now(),
        pending["sums"],
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

    # The broker's sums insured. The extracted figure is only a pre-fill: what
    # the form says is what gets priced, and an edited figure drops the
    # extraction's basis rather than mislabelling the broker's number.
    confirmed_sums: list[SumInsured] = []
    for section_id, extracted in pending["sums"].items():
        field = f"sum_insured_{section_id.value}"
        amount = _parse_amount(form.get(field)) if field in form else extracted.amount
        basis = extracted.basis if amount == extracted.amount else "Entered by the broker at the needs gate."
        confirmed_sums.append(SumInsured(section=section_id, amount=amount, basis=basis if amount is not None else ""))

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
        "sums": confirmed_sums, "usage": llm.usage_summary(),
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
    # Deterministic pricing draft from the approved findings and the sums the
    # broker confirmed at gate 1. Loadings come from the band table; the Price
    # gate is where the underwriter confirms or overrides them.
    case.pricing = pricing.price_case(pending["needs"], approved, pending.get("sums", []))
    memory.store(case)
    DRAFTS.pop(draft_id, None)
    try:
        proposal = memory.propose_reflection(case)
        if proposal is not None:
            PENDING_LEARNING[case.case_id] = proposal
    except Exception:
        LEARNING_NOTES[case.case_id] = (
            "Case approved. The learning proposal is temporarily unavailable and can be retried later."
        )
    return RedirectResponse(url=f"/cases/{case.case_id}/pricing", status_code=303)


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


@app.get("/cases/{case_id}/pricing", response_class=HTMLResponse)
def pricing_gate(case_id: str) -> HTMLResponse:
    """Human gate 3: the deterministic premium per required section, loadings
    confirmable or overridable before the case report is finalised."""
    case = memory.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    if case.pricing is None:
        # Pre-pricing case (old or chat-ingested): draft a table now. No sums
        # were confirmed at a needs gate, so every line shows as not priced.
        case.pricing = pricing.price_case(case.needs, case.approved_findings, [])
    return HTMLResponse(render_pricing(case, _now()))


@app.post("/cases/{case_id}/pricing", response_class=HTMLResponse)
async def save_case_pricing(case_id: str, request: Request) -> HTMLResponse:
    case = memory.get_case(case_id)
    if case is None or case.pricing is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    form = await request.form()

    # Premiums are recomputed server-side from the stored sums and the current
    # config — the form only carries the loadings the underwriter settled on.
    sums = [SumInsured(section=l.section, amount=l.sum_insured, basis=l.basis)
            for l in case.pricing.lines]
    overrides: dict = {}
    for line in case.pricing.lines:
        raw = (form.get(f"loading_{line.section.value}") or "").strip()
        if not raw:
            continue
        try:
            overrides[line.section] = float(raw)
        except ValueError:
            return HTMLResponse(
                render_error("Pricing needs attention",
                             f"The loading for {section(line.section).name} is not a number: {raw!r}.",
                             f"/cases/{case_id}/pricing"),
                status_code=400,
            )
    case.pricing = pricing.price_case(case.needs, case.approved_findings, sums, overrides)
    memory.store(case)
    return HTMLResponse(render_report(
        case, "stored", _now(), LEARNING_NOTES.pop(case_id, None), PENDING_LEARNING.get(case_id)
    ))


@app.get("/rates", response_class=HTMLResponse)
def rates_page(saved: int = 0) -> HTMLResponse:
    return HTMLResponse(render_rates(pricing.load_rates(), pricing.load_loadings(), bool(saved)))


@app.post("/rates")
async def save_rates_config(request: Request) -> Response:
    form = await request.form()
    rates = pricing.load_rates()
    loadings = pricing.load_loadings()
    try:
        for section_id, entry in rates.items():
            raw = (form.get(f"rate_{section_id}") or "").strip()
            if raw:
                entry["rate"] = float(raw)
                if entry["rate"] < 0:
                    raise ValueError(f"the {section(SectionId(section_id)).name} rate cannot be negative")
        for band in pricing.BANDS:
            raw = (form.get(f"loading_{band}") or "").strip()
            if raw:
                loadings[band] = float(raw)
    except ValueError as exc:
        return HTMLResponse(
            render_error("Rates need attention", f"Check the values entered: {exc}.", "/rates"),
            status_code=400,
        )
    pricing.save_rates(rates)
    pricing.save_loadings(loadings)
    return RedirectResponse(url="/rates?saved=1", status_code=303)


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


@app.get("/cases/{case_id}/pdf")
def case_pdf_download(case_id: str) -> Response:
    case = memory.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return Response(
        content=case_pdf(case, _now()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_filename(case)}"'},
    )


@app.post("/cases/{case_id}/confirm")
def confirm_ingested_case(case_id: str) -> RedirectResponse:
    """Human confirmation of a provisional (chat-ingested) case — docs/SOLUTION_DESIGN.md §4.4."""
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
    LEARNING_NOTES.clear()
    return RedirectResponse(url="/", status_code=303)
