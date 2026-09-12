"""
PDF export of an approved case: case_pdf.html rendered with Jinja, then
converted with xhtml2pdf (pure Python — no browser or system libraries).

The PDF is the insurer-facing document, mirroring report.html: Part 1 the
quotation (summary, itemised sections, terms), Part 2 the risk assessment
behind it (findings per section: title, severity, reasoning). Internal
material — factor slugs, precedent ids, confidence, evidence quotes,
reviewer edits, loading overrides — is deliberately left out.
"""

from __future__ import annotations

import io
from pathlib import Path

from xhtml2pdf import pisa

from .models import CaseRecord
from .report import _env, document_context
from .sections import section

_LOGO = Path(__file__).parent / "static" / "converge-underwriting-logo.png"

def render_case_pdf_html(case: CaseRecord, generated_at: str) -> str:
    return _env.get_template("case_pdf.html").render(
        generated_at=generated_at, section=section,
        logo_path=str(_LOGO) if _LOGO.exists() else "",
        **document_context(case),
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
