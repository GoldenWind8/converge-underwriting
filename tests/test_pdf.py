from fastapi.testclient import TestClient

from app import memory
from app.models import (CaseRecord, ClientProfile, Requirement, RiskFinding,
                        SectionNeed, Severity)
from app.pdf import case_pdf, pdf_filename, render_case_pdf_html
from app.sections import SectionId

CASE = CaseRecord(
    case_id="C-0042",
    created_at="2026-08-27T18:35:44",
    source="assessment",
    client_profile=ClientProfile(business_name="XYZ Shoes", industry="shoe manufacturing", employees=140),
    summary="A 24-hour shoe factory using flammable liquids.",
    needs=[
        SectionNeed(section=SectionId.fire, requirement=Requirement.required, reason="Owns plant and stock."),
        SectionNeed(section=SectionId.glass, requirement=Requirement.not_applicable, reason="No glass."),
    ],
    approved_findings=[RiskFinding(
        factor_name="uncertified_electrical_installation", section=SectionId.fire,
        severity=Severity.high, assessment_note="Below standard for a manufacturing occupancy.",
        evidence_quote="Electrical CoC current, and dated: No",
        reasoning="An uncertified installation is an unmanaged ignition source.",
        precedent_case_ids=["C-0001"], confidence=0.9,
    )],
    final_band="Elevated", checked_by="Sashin",
)


def test_pdf_html_is_insurer_facing():
    html = render_case_pdf_html(CASE, "2026-08-27 19:00")

    assert "XYZ Shoes" in html and "Risk assessment" in html
    assert "Uncertified electrical installation" in html, "factor titles are humanised"
    assert "uncertified_electrical_installation" not in html, "no internal slugs"
    assert "C-0001" not in html, "no precedent codes"
    assert "Prepared by Sashin" in html
    assert "Fire" in html and "2. Fire" not in html, "section numbers are internal"
    assert "Glass" not in html, "not-applicable sections stay off the PDF"
    assert "Electrical CoC current, and dated: No" not in html, "evidence quotes are internal"
    assert "Below standard for a manufacturing occupancy" not in html, "one statement per finding"
    assert "No premium quoted" in html, "an unpriced case still says so on page one"


def test_pdf_leads_with_the_quote():
    from app.models import CasePricing, PricedSection

    priced = CASE.model_copy(update={"pricing": CasePricing(
        lines=[
            PricedSection(section=SectionId.fire, band="Elevated", risk_score=62.5,
                          rate=0.40, table_loading=10, applied_loading=15,
                          sum_insured=18_000_000, basis="Plant + stock",
                          base_premium=72_000, adjusted_premium=82_800),
            PricedSection(section=SectionId.fidelity, band="Low", risk_score=12.5,
                          rate=0.50, table_loading=-10, applied_loading=-10),
        ],
        base_total=72_000, adjusted_total=82_800,
    )})

    # Amounts are rendered with non-breaking spaces so they never wrap in the PDF.
    html = render_case_pdf_html(priced, "2026-08-27 19:00").replace("&nbsp;", " ")

    assert html.index(">Quote<") < html.index("Risk assessment")
    assert "R 82 800" in html and "R 18 000 000" in html
    assert "R 72 000" not in html, "the base premium is internal"
    assert "band table" not in html, "the applied loading is the quoted loading; overrides are internal"
    assert "+15%" in html and "Elevated" in html
    assert "Fidelity" not in html and "Not priced" not in html, "unpriced lines stay off the PDF"
    # Bands drive loadings; numeric scores stay off the client PDF.
    assert "62.50" not in html and "pts" not in html
    assert "subject to the insurer" in html


def test_case_pdf_produces_a_pdf():
    data = case_pdf(CASE, "2026-08-27 19:00")
    assert data.startswith(b"%PDF")
    assert pdf_filename(CASE) == "Converge-Underwriting-C-0042-XYZ-Shoes.pdf"


def test_pdf_route_downloads_stored_case(fake_llm):
    from app.main import app
    memory.store(CASE)
    client = TestClient(app)

    response = client.get(f"/cases/{CASE.case_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Converge-Underwriting-C-0042-XYZ-Shoes.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert client.get("/cases/C-9999/pdf").status_code == 404
