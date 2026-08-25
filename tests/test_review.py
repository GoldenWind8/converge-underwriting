import os

import pytest
from starlette.datastructures import FormData
from fastapi.testclient import TestClient

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app import memory
from app.main import PENDING_LEARNING, _apply_review, app
from app.memory import LearningProposal
from app.models import (CaseRecord, ClientProfile, RiskFinding, Severity)
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


def test_underwriter_accepts_learning_before_it_becomes_active():
    profile = ClientProfile(business_name="A", industry="restaurant", summary="Restaurant")
    case = CaseRecord(
        case_id="C-0001", created_at="2026-08-07T10:00:00", source="assessment",
        client_profile=profile, summary=profile.summary,
        draft_findings=[_finding()], approved_findings=[_finding()],
        final_band="Elevated",
    )
    memory.store(case)
    proposal = LearningProposal(
        case_id=case.case_id, current_playbook=memory.load_playbook(),
        proposed_playbook="# Underwriting Playbook\n\n## PB-001 · [fire] Fire\nRequire protection.\n",
        change_note="Added PB-001.",
    )
    PENDING_LEARNING[case.case_id] = proposal

    response = TestClient(app).post(
        f"/learning/{case.case_id}",
        data={"action": "accept", "proposed_playbook": proposal.proposed_playbook},
    )

    assert response.status_code == 200
    assert "PB-001" in memory.load_playbook()
    assert case.case_id not in PENDING_LEARNING


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


def test_converge_brand_asset_is_served():
    response = TestClient(app).get("/static/converge-underwriting-logo.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"Converge Underwriting" in response.content
