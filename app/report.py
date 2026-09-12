"""
Rendering: templates in, HTML out. No logic beyond display grouping.

- index.html     landing page (with an optional one-click sample application)
- needs.html     the needs determination table (human gate 1)
- pricing.html   the Price gate (human gate 2): ratings + premiums, and the
                 post-approval "adjust pricing" view of a stored case
- review.html    findings with evidence — drill-down from the Price gate
- report.html    the insurer document for an approved case: Part 1 the quotation,
                 Part 2 the risk assessment behind it (case_pdf.html mirrors it)
- cases.html     case-memory listing (+ the deleted history log)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .guardrails import GuardrailResult, band_for_section
from .models import (CasePricing, CaseRecord, ClientProfile,
                     NeedsDetermination, RiskAssessmentDraft, RiskFinding,
                     SectionNeed)
from .pricing import config_dir, load_loadings, load_rates
from .sections import (COVER_SECTIONS, MOTOR_SUB_TYPE_NOTES, SectionId,
                       section)


def _rand(value) -> str:
    """1234567 -> 'R 1 234 567' (space-grouped, whole rand)."""
    if value is None:
        return "—"
    return "R " + f"{round(value):,}".replace(",", " ")


def load_factor_labels() -> Dict[str, str]:
    """Optional snake_case factor -> plain-English label overrides
    (config/factor_labels.json). Factors not listed are humanised."""
    path = config_dir() / "factor_labels.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _label(factor_name: str) -> str:
    """'uncertified_gas_installation' -> 'Uncertified gas installation',
    unless the labels file says otherwise. Storage stays snake_case."""
    override = load_factor_labels().get(factor_name)
    if override:
        return override
    return factor_name.replace("_", " ").strip().capitalize()


def _short(finding: RiskFinding) -> str:
    """One-line description for the Price gate: the assessment note, else the
    first sentence of the reasoning."""
    if finding.assessment_note:
        return finding.assessment_note
    return re.split(r"(?<=[.!?])\s", finding.reasoning.strip(), maxsplit=1)[0]


_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)
_env.filters["rand"] = _rand
_env.filters["label"] = _label
_env.filters["short"] = _short
_env.globals.update(
    cover_sections=COVER_SECTIONS,
    motor_sub_type_notes=MOTOR_SUB_TYPE_NOTES,
    severity_values=["low", "medium", "high", "severe"],
    section=section,
)


def _section_groups(findings: List[RiskFinding], needs: List[SectionNeed]) -> list:
    """Group findings by cover section, preserving order and each finding's
    global index (the review form fields are indexed over the flat list)."""
    by_need = {n.section: n for n in needs}
    groups: list = []
    for index, finding in enumerate(findings):
        if not groups or groups[-1]["cover"].id != finding.section:
            groups.append({
                "cover": section(finding.section),
                "need": by_need.get(finding.section),
                "items": [],
            })
        groups[-1]["items"].append((index, finding))
    return groups


def render_index(sample: str = "", case_count: int = 0) -> str:
    return _env.get_template("index.html").render(sample=sample, case_count=case_count)


def render_needs(needs_id: str, determination: NeedsDetermination, profile,
                 engine: str, generated_at: str,
                 sums: Optional[dict] = None) -> str:
    return _env.get_template("needs.html").render(
        needs_id=needs_id, determination=determination, profile=profile,
        engine=engine, generated_at=generated_at, sums=sums or {},
    )


def render_review(draft_id: str, draft: RiskAssessmentDraft, result: GuardrailResult,
                  engine: str, generated_at: str, raw_text: str = "",
                  needs: Optional[List[SectionNeed]] = None,
                  usage: Optional[dict] = None) -> str:
    needs = needs or []
    return _env.get_template("review.html").render(
        draft_id=draft_id, draft=draft, result=result, engine=engine,
        generated_at=generated_at, raw_text=raw_text, needs=needs,
        groups=_section_groups(result.findings, needs), usage=usage,
    )


def document_context(case: CaseRecord) -> dict:
    """What report.html and case_pdf.html both need: the priced lines (Part 1),
    the findings grouped by section with each section's band (Part 2)."""
    priced = [l for l in case.pricing.lines if l.base_premium is not None] if case.pricing else []
    bands = {line.section: line.band for line in priced}
    groups = _section_groups(case.approved_findings, case.needs)
    for group in groups:
        group["band"] = bands.get(group["cover"].id) or band_for_section([f for _, f in group["items"]])
    return {
        "case": case,
        "priced": priced,
        "groups": groups,
        "sub_types": {n.section: n.motor_sub_type.value.replace("-", " ").capitalize()
                      for n in case.needs if n.motor_sub_type},
    }


def render_report(case: CaseRecord, engine: str, generated_at: str) -> str:
    return _env.get_template("report.html").render(
        engine=engine, generated_at=generated_at, **document_context(case),
    )


def render_pricing(priced: CasePricing, findings: List[RiskFinding], generated_at: str,
                   draft_id: Optional[str] = None, profile: Optional[ClientProfile] = None,
                   usage: Optional[dict] = None, case: Optional[CaseRecord] = None) -> str:
    """The Price gate. With draft_id: the approval gate for an unstored draft
    (ratings editable). With case: adjusting a stored case's pricing (ratings
    read-only). Findings are listed per section with their global index —
    the severity_<i> form fields are indexed over the flat list."""
    by_section: dict = {}
    for index, f in enumerate(findings):
        by_section.setdefault(f.section, []).append((index, f))
    return _env.get_template("pricing.html").render(
        pricing=priced, findings_by_section=by_section, generated_at=generated_at,
        draft_id=draft_id, case=case, profile=profile or (case.client_profile if case else None),
        usage=usage, rates=load_rates(), loadings=load_loadings(),
    )


def render_rates(rates: dict, loadings: dict, saved: bool = False, back: str = "") -> str:
    band_order = ["Low", "Moderate", "Elevated", "High"]
    return _env.get_template("rates.html").render(
        rates=rates, loadings=loadings, band_order=band_order, saved=saved, back=back,
    )


def render_cases(cases: List[CaseRecord], deleted: Optional[List[CaseRecord]] = None) -> str:
    return _env.get_template("cases.html").render(cases=cases, deleted=deleted or [])


def render_error(title: str, message: str, retry_href: str = "/") -> str:
    return _env.get_template("error.html").render(
        title=title, message=message, retry_href=retry_href
    )
