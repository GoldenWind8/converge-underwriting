"""The whole pipeline through the HTTP layer: submit -> needs table (gate 1)
-> per-section assessment -> Price gate (gate 2: ratings, checked by) ->
approved case with needs, a severity-derived band and its pricing."""

import os
import re

from fastapi.testclient import TestClient

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app import memory
from app.main import app
from app.models import (ClientProfile, NeedsDetermination, Requirement,
                        RiskFinding, SectionAssessment, SectionNeed, Severity,
                        SumInsured, SumsInsured)
from app.sections import SectionId

RAW = (
    "Business name: Kaap Timber\n"
    "Trade: timber merchant\n"
    "Stock: sawn timber and adhesives in a side store\n"
    "Fire protection: no sprinklers, no fire detection\n"
)

PROFILE = ClientProfile(business_name="Kaap Timber", industry="timber merchant",
                        covers_requested=["Fire"], summary="Timber merchant; combustible stock.")

NEEDS = [
    SectionNeed(section=SectionId.fire, requirement=Requirement.required,
                reason="Combustible stock on site."),
    SectionNeed(section=SectionId.motor, requirement=Requirement.not_applicable,
                reason="No vehicles in the submission."),
]


def _finding(**overrides):
    base = dict(
        factor_name="no_fire_detection", section=SectionId.fire, severity=Severity.high,
        evidence_quote="no sprinklers, no fire detection",
        reasoning="Combustible stock with no detection.", confidence=0.9,
    )
    base.update(overrides)
    return RiskFinding(**base)


def _register(fake_llm, sums):
    fake_llm.register(ClientProfile, PROFILE)
    fake_llm.register(NeedsDetermination, NeedsDetermination(
        business_note="A timber merchant.", needs=NEEDS))
    fake_llm.register(SectionAssessment, SectionAssessment(findings=[_finding()]))
    fake_llm.register(SumsInsured, SumsInsured(items=sums))


def test_full_flow_through_all_gates(fake_llm):
    _register(fake_llm, [SumInsured(section=SectionId.fire, amount=1_000_000, basis="Stock R1 000 000")])
    client = TestClient(app)

    # Submit -> needs table (gate 1)
    response = client.post("/assess", data={"raw_text": RAW})
    assert response.status_code == 200
    match = re.search(r'action="/needs/([0-9a-f]+)"', response.text)
    assert match, "the needs page must post back to its confirm route"
    needs_id = match.group(1)
    assert response.text.count("requirement_") == 18

    # Gate 1: confirm as-is -> straight to the Price gate.
    form = {"requirement_fire": "required", "requirement_theft": "not-applicable"}
    response = client.post(f"/needs/{needs_id}", data=form)
    assert response.status_code == 200
    match = re.search(r'action="/drafts/([0-9a-f]+)/price"', response.text)
    assert match, "the needs gate lands on the Price gate"
    draft_id = match.group(1)
    assert "Pricing engine" in response.text
    assert "R 2 000" in response.text  # 1m x 0.20% fire base premium
    assert "No fire detection" in response.text and 'name="severity_0"' in response.text
    assert "Combustible stock with no detection." in response.text

    # Drill-down: the review page shows evidence; a why-note travels with a rating change.
    response = client.get(f"/review/{draft_id}")
    assert response.status_code == 200 and 'name="note_0"' in response.text
    response = client.post(f"/review/{draft_id}", data={
        "keep_0": "on", "severity_0": "severe",
        "note_0": "Timber plus no detection is a decline without remediation.",
    })
    assert response.status_code == 200 and "Pricing engine" in response.text, "Save & go back"
    assert 'value="severe" selected' in response.text

    # Gate 2: override the fire loading (band table says +25), sign, approve -> report.
    response = client.post(f"/drafts/{draft_id}/price", data={
        "checked_by": "Cameron", "add_to_memory": "on", "severity_0": "severe", "loading_fire": "30",
    })
    assert response.status_code == 200
    assert "Decision recorded" in response.text
    assert "Checked by Cameron" in response.text
    assert "band table: +25%" in response.text, "a manual override is disclosed, not silent"

    case = memory.get_case("C-0001")
    assert case is not None
    assert case.checked_by == "Cameron" and not case.provisional
    assert case.final_band == "High"  # one severe finding
    assert case.approved_findings[0].severity == Severity.severe
    assert case.corrections[0].note == "Timber plus no detection is a decline without remediation."
    assert len(case.needs) == 18, "the confirmed needs table is stored with the case"
    assert case.needs[1].requirement == Requirement.required  # fire, confirmed at gate 1

    fire_line = next(l for l in case.pricing.lines if l.section == SectionId.fire)
    assert fire_line.band == "High"
    assert fire_line.sum_insured == 1_000_000
    assert fire_line.base_premium == 2_000
    assert fire_line.table_loading == 25 and fire_line.applied_loading == 30
    assert fire_line.overridden
    assert fire_line.adjusted_premium == 2_600
    assert case.pricing.adjusted_total == 2_600

    # Post-approval: adjust pricing on the stored case.
    response = client.post("/cases/C-0001/pricing", data={"loading_fire": "25"})
    assert response.status_code == 200 and "Decision recorded" in response.text
    assert not memory.get_case("C-0001").pricing.lines[0].overridden


def test_confirming_needs_with_nothing_required_is_rejected(fake_llm):
    _register(fake_llm, [])
    client = TestClient(app)
    response = client.post("/assess", data={"raw_text": RAW})
    needs_id = re.search(r'action="/needs/([0-9a-f]+)"', response.text).group(1)

    form = {f"requirement_{s.value}": "not-applicable" for s in SectionId}
    response = client.post(f"/needs/{needs_id}", data=form)
    assert response.status_code == 400
    assert "at least one" in response.text


def test_required_section_without_a_sum_insured_is_rejected_at_the_needs_gate(fake_llm):
    _register(fake_llm, [])  # nothing stated in the submission
    client = TestClient(app)
    response = client.post("/assess", data={"raw_text": RAW})
    needs_id = re.search(r'action="/needs/([0-9a-f]+)"', response.text).group(1)

    response = client.post(f"/needs/{needs_id}", data={"requirement_fire": "required", "requirement_theft": "required"})
    assert response.status_code == 400
    assert "Fire, Theft" in response.text
    assert not [c for c in fake_llm.calls if c[0] == "SectionAssessment"], "rejected before any assessment call"

    # The broker fills the figures in; the retry page shows what they chose.
    retry = client.get(f"/needs/{needs_id}")
    assert 'name="requirement_theft"' in retry.text
    response = client.post(f"/needs/{needs_id}", data={
        "requirement_fire": "required", "requirement_theft": "required",
        "sum_insured_fire": "R1 000 000", "sum_insured_theft": "250,000",
    })
    assert response.status_code == 200 and "Pricing engine" in response.text
    assert "R 250 000" in response.text
    assert "Entered by the broker at the needs gate." in response.text
