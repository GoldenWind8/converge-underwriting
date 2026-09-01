"""The whole pipeline through the HTTP layer: submit -> needs table (gate 1)
-> per-section assessment -> review (gate 2) -> approved case with needs and
a severity-derived band."""

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


def test_full_flow_through_all_gates(fake_llm):
    fake_llm.register(ClientProfile, PROFILE)
    fake_llm.register(NeedsDetermination, NeedsDetermination(
        business_note="A timber merchant.", needs=NEEDS))
    fake_llm.register(SectionAssessment, SectionAssessment(findings=[_finding()]))
    fake_llm.register(SumsInsured, SumsInsured(items=[
        SumInsured(section=SectionId.fire, amount=1_000_000, basis="Stock R1 000 000"),
    ]))

    client = TestClient(app)

    # Submit -> needs table (gate 1)
    response = client.post("/assess", data={"raw_text": RAW})
    assert response.status_code == 200
    match = re.search(r'action="/needs/([0-9a-f]+)"', response.text)
    assert match, "the needs page must post back to its confirm route"
    needs_id = match.group(1)
    assert response.text.count("requirement_") == 18

    # Gate 1: flip the model's 'not-applicable' Motor to required? No — confirm as-is,
    # but demonstrate an override: mark Theft required too.
    form = {"requirement_fire": "required", "requirement_theft": "not-applicable"}
    response = client.post(f"/needs/{needs_id}", data=form)
    assert response.status_code == 200
    match = re.search(r'name="draft_id" value="([0-9a-f]+)"', response.text)
    assert match, "the review page must carry the draft id"
    draft_id = match.group(1)
    assert "no_fire_detection" in response.text
    assert 'name="note_0"' in response.text

    # Gate 2: bump the severity with a why-note and approve -> Price gate.
    response = client.post("/approve", data={
        "draft_id": draft_id, "keep_0": "on", "severity_0": "severe",
        "note_0": "Timber plus no detection is a decline without remediation.",
    })
    assert response.status_code == 200
    assert "Pricing engine" in response.text, "approval lands on the Price gate"
    assert "R 2 000" in response.text  # 1m x 0.20% fire base premium

    # Gate 3: override the fire loading (band table says +25) and save.
    response = client.post("/cases/C-0001/pricing", data={"loading_fire": "30"})
    assert response.status_code == 200
    assert "Underwriting decision recorded" in response.text
    assert "band table: +25%" in response.text, "a manual override is disclosed, not silent"

    case = memory.get_case("C-0001")
    assert case is not None
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


def test_confirming_needs_with_nothing_required_is_rejected(fake_llm):
    fake_llm.register(ClientProfile, PROFILE)
    fake_llm.register(NeedsDetermination, NeedsDetermination(needs=[]))
    fake_llm.register(SumsInsured, SumsInsured(items=[]))

    client = TestClient(app)
    response = client.post("/assess", data={"raw_text": RAW})
    needs_id = re.search(r'action="/needs/([0-9a-f]+)"', response.text).group(1)

    form = {f"requirement_{s.value}": "not-applicable" for s in SectionId}
    response = client.post(f"/needs/{needs_id}", data=form)
    assert response.status_code == 400
    assert "at least one" in response.text
