"""
PDF export of an approved case: case_pdf.html rendered with Jinja, then
converted with xhtml2pdf (pure Python — no browser or system libraries).

The PDF is the client-facing view of a case: section names, plain-English
factor titles, severities, reasoning and the quoted evidence. Internal codes
(factor slugs, playbook rule ids, precedent case ids, confidence, reviewer
edits) are deliberately left out.
"""

from __future__ import annotations

import io
from pathlib import Path

from xhtml2pdf import pisa

from .models import CaseRecord, Requirement
from .report import _env, _section_groups
from .sections import section

_LOGO = Path(__file__).parent / "static" / "converge-underwriting-logo.png"

REQUIREMENT_LABELS = {
    Requirement.required.value: "Required",
    Requirement.consider.value: "Worth considering",
    Requirement.not_applicable.value: "Not applicable",
}


def render_case_pdf_html(case: CaseRecord, generated_at: str) -> str:
    return _env.get_template("case_pdf.html").render(
        case=case,
        generated_at=generated_at,
        groups=_section_groups(case.approved_findings, case.needs),
        sections_assessed=sum(1 for n in case.needs if n.requirement == Requirement.required),
        requirement_labels=REQUIREMENT_LABELS,
        section=section,
        logo_path=str(_LOGO) if _LOGO.exists() else "",
    )


def case_pdf(case: CaseRecord, generated_at: str) -> bytes:
    html = render_case_pdf_html(case, generated_at)
    buffer = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF conversion failed with {result.err} error(s).")
    return buffer.getvalue()


def pdf_filename(case: CaseRecord) -> str:
    name = (case.client_profile.business_name or "case").strip()
    safe = "".join(c if c.isalnum() else "-" for c in name).strip("-") or "case"
    return f"Converge-Underwriting-{case.case_id}-{safe}.pdf"
