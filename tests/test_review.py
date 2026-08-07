import os

from starlette.datastructures import FormData
from fastapi.testclient import TestClient

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app import memory
from app.main import PENDING_LEARNING, _apply_review, app
from app.memory import LearningProposal
from app.models import CaseRecord, ClientProfile, RiskFinding, Severity


RAW = "Fire extinguishers: No\nGas certificate: Missing"


def _finding() -> RiskFinding:
    return RiskFinding(
        factor_name="no_extinguishers", section="Fire", severity=Severity.high,
        suggested_points=15, evidence_quote="Fire extinguishers: No",
        reasoning="No first response protection.", confidence=0.9,
    )


def test_reviewer_added_finding_keeps_verbatim_evidence():
    form = FormData([
        ("keep_0", "on"), ("severity_0", "high"), ("points_0", "15"),
        ("new_factor_name", "missing gas certificate"),
        ("new_section", "Fire"), ("new_severity", "medium"),
        ("new_points", "10"), ("new_reasoning", "Certification is absent."),
        ("new_evidence_quote", "Gas certificate: Missing"),
    ])

    approved, corrections = _apply_review(form, [_finding()], RAW)

    assert approved[-1].factor_name == "missing_gas_certificate"
    assert approved[-1].evidence_quote == "Gas certificate: Missing"
    assert corrections[-1].type == "added"


def test_underwriter_accepts_learning_before_it_becomes_active():
    profile = ClientProfile(business_name="A", industry="restaurant", summary="Restaurant")
    case = CaseRecord(
        case_id="C-0001", created_at="2026-08-07T10:00:00", source="assessment",
        client_profile=profile, summary=profile.summary,
        draft_findings=[_finding()], approved_findings=[_finding()],
        final_score=15, final_band="Moderate",
    )
    memory.store(case)
    proposal = LearningProposal(
        case_id=case.case_id, current_playbook=memory.load_playbook(),
        proposed_playbook="# Underwriting Playbook\n\n## PB-001 · Fire\nRequire protection.\n",
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
