import os

import pytest
from starlette.datastructures import FormData
from fastapi.testclient import TestClient

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app import guardrails, memory
from app.guardrails import GuardrailResult
from app.main import DRAFTS, _apply_ratings, _apply_review, app
from app.models import (CaseRecord, ClientProfile, Requirement,
                        RiskAssessmentDraft, RiskFinding, SectionNeed,
                        Severity, SumInsured)
from app.sections import SectionId


RAW = "Fire extinguishers: No\nGas certificate: Missing since the refit"


def _finding() -> RiskFinding:
    return RiskFinding(
        factor_name="no_extinguishers", section=SectionId.fire, severity=Severity.high,
        evidence_quote="Fire extinguishers: No",
        reasoning="No first response protection.", confidence=0.9,
    )


def test_compound_edit_records_severity_change_with_the_why_note():
    form = FormData([
        ("keep_0", "on"), ("severity_0", "severe"),
        ("note_0", "Extinguishers are a licensing condition for this trade."),
    ])

    approved, corrections = _apply_review(form, [_finding()], RAW)

    assert approved[0].severity == Severity.severe
    assert corrections[0].type == "severity_changed"
    assert corrections[0].detail == "high -> severe"
    assert corrections[0].note == "Extinguishers are a licensing condition for this trade."


def test_removal_keeps_the_reviewers_note():
    form = FormData([("note_0", "Duplicate of the gas finding.")])
    approved, corrections = _apply_review(form, [_finding()], RAW)
    assert approved == []
    assert corrections[0].type == "removed"
    assert corrections[0].note == "Duplicate of the gas finding."


def test_reviewer_added_finding_keeps_verbatim_evidence_and_section():
    form = FormData([
        ("keep_0", "on"), ("severity_0", "high"),
        ("new_factor_name", "missing gas certificate"),
        ("new_section", "fire"), ("new_severity", "medium"),
        ("new_reasoning", "Certification is absent."),
        ("new_evidence_quote", "Gas certificate: Missing since the refit"),
    ])

    approved, corrections = _apply_review(form, [_finding()], RAW)

    added = approved[-1]
    assert added.factor_name == "missing_gas_certificate"
    assert added.section == SectionId.fire
    assert added.evidence_quote == "Gas certificate: Missing since the refit"
    assert corrections[-1].type == "added"


def test_reviewer_added_finding_rejects_insubstantial_evidence():
    form = FormData([
        ("new_factor_name", "invented_factor"),
        ("new_section", "fire"), ("new_severity", "high"),
        ("new_evidence_quote", "No"),  # present in the source, but not evidence
    ])
    with pytest.raises(Exception) as excinfo:
        _apply_review(form, [], RAW)
    assert "substantial" in str(excinfo.value.detail)


def test_price_gate_ratings_keep_every_finding_and_record_changes():
    form = FormData([("severity_0", "medium")])  # no keep_ fields on the price page
    approved, corrections = _apply_ratings(form, [_finding()])
    assert [f.severity for f in approved] == [Severity.medium]
    assert corrections[0].type == "severity_changed" and corrections[0].detail == "high -> medium"
    assert _apply_ratings(FormData([]), [_finding()])[1] == []


def _draft(draft_id="d1", findings=None):
    findings = findings if findings is not None else [_finding()]
    profile = ClientProfile(business_name="A", industry="restaurant", summary="Restaurant")
    result = GuardrailResult(findings=findings, band=guardrails.band_for_findings(findings))
    DRAFTS[draft_id] = {
        "draft": RiskAssessmentDraft(client_profile=profile, findings=findings),
        "result": result, "findings": list(findings), "corrections": [],
        "engine": "fake", "raw_text": RAW,
        "needs": [SectionNeed(section=SectionId.fire, requirement=Requirement.required, reason="x")],
        "sums": [SumInsured(section=SectionId.fire, amount=1_000_000, basis="Stock")],
        "usage": {"calls": 1},
    }
    return draft_id


def test_review_drill_down_writes_back_into_the_draft_and_returns_to_the_price_gate():
    draft_id = _draft()
    client = TestClient(app)

    response = client.post(f"/review/{draft_id}", data={
        "keep_0": "on", "severity_0": "severe", "note_0": "Licensing condition.",
        "new_factor_name": "missing gas certificate", "new_section": "fire", "new_severity": "medium",
        "new_evidence_quote": "Gas certificate: Missing since the refit",
    }, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/drafts/{draft_id}/price"
    pending = DRAFTS[draft_id]
    assert [f.factor_name for f in pending["findings"]] == ["no_extinguishers", "missing_gas_certificate"]
    assert [c.type for c in pending["corrections"]] == ["severity_changed", "added"]
    assert pending["result"].findings[0].severity == Severity.high, "the original draft is untouched"
    assert memory.all_cases() == [], "nothing is stored from the drill-down"

    page = client.get(f"/drafts/{draft_id}/price")
    assert 'name="severity_1"' in page.text, "the added finding is now rated on the price page"


def test_approving_at_the_price_gate_requires_checked_by_and_stores_the_case():
    draft_id = _draft()
    client = TestClient(app)

    rejected = client.post(f"/drafts/{draft_id}/price", data={"severity_0": "high"})
    assert rejected.status_code == 400 and "Checked by" in rejected.text
    assert draft_id in DRAFTS

    response = client.post(f"/drafts/{draft_id}/price", data={
        "checked_by": "Cameron", "add_to_memory": "on", "severity_0": "severe", "loading_fire": "25",
    }, follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/cases/C-0001"
    assert draft_id not in DRAFTS
    case = memory.get_case("C-0001")
    assert case.checked_by == "Cameron" and not case.provisional
    assert case.approved_findings[0].severity == Severity.severe
    assert case.corrections[0].detail == "high -> severe"
    assert case.draft_findings[0].severity == Severity.high
    assert case.final_band == "High"
    assert case.pricing.lines[0].band == "High" and not case.pricing.lines[0].overridden


def test_approving_without_add_to_memory_stores_a_provisional_case():
    draft_id = _draft()
    client = TestClient(app)
    client.post(f"/drafts/{draft_id}/price", data={"checked_by": "Cameron"}, follow_redirects=False)
    case = memory.get_case("C-0001")
    assert case.provisional, "not in case memory until confirmed on /cases"
    assert memory.active_cases() == []
    client.post(f"/cases/{case.case_id}/confirm", follow_redirects=False)
    assert memory.get_case("C-0001").provisional is False


def test_confirming_a_provisional_case_activates_it():
    profile = ClientProfile(business_name="B", industry="bakery", summary="Bakery")
    case = CaseRecord(
        case_id="C-0009", created_at="2026-08-07T10:00:00", source="chat_ingestion",
        client_profile=profile, summary=profile.summary,
        approved_findings=[_finding()], final_band="Elevated", provisional=True,
    )
    memory.store(case)

    response = TestClient(app).post(f"/cases/{case.case_id}/confirm", follow_redirects=False)

    assert response.status_code == 303
    assert memory.get_case(case.case_id).provisional is False


def test_deleting_a_case_needs_a_name_and_a_reason():
    profile = ClientProfile(business_name="B", industry="bakery", summary="Bakery")
    memory.store(CaseRecord(case_id="C-0004", created_at="2026-08-07T10:00:00", source="assessment",
                            client_profile=profile, summary=profile.summary,
                            approved_findings=[_finding()], final_band="Elevated"))
    client = TestClient(app)

    rejected = client.post("/cases/C-0004/delete", data={"deleted_by": "Cameron"})
    assert rejected.status_code == 400
    assert memory.get_case("C-0004").deleted_at is None

    response = client.post("/cases/C-0004/delete",
                           data={"deleted_by": "Cameron", "reason": "Client withdrew."},
                           follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/cases"
    assert memory.get_case("C-0004").deleted_reason == "Client withdrew."
    assert memory.all_cases() == []
    listing = client.get("/cases").text
    assert "Client withdrew." in listing
    assert client.get("/cases/C-0004").status_code == 200, "the deleted case's report stays readable"
    assert client.post("/cases/C-9999/delete", data={"deleted_by": "x", "reason": "y"}).status_code == 404


def test_converge_brand_asset_is_served():
    response = TestClient(app).get("/static/converge-underwriting-logo.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"Converge Underwriting" in response.content


def test_rates_save_and_go_back_returns_to_a_local_page_and_confirms_a_placeholder():
    from app import pricing
    client = TestClient(app)

    response = client.post(
        "/rates",
        data={"rate_motor": "3.5", "confirmed_motor": "1", "next": "/cases/C-0001/pricing", "action": "back"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/cases/C-0001/pricing"
    assert pricing.load_rates()["motor"] == {"rate": 3.5, "basis": pricing.DEFAULT_RATES["motor"]["basis"]}

    offsite = client.post("/rates", data={"next": "https://evil.example", "action": "back"}, follow_redirects=False)
    assert offsite.headers["location"] == "/rates?saved=1"
