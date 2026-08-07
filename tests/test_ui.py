from app.guardrails import GuardrailResult
from app.memory import LearningProposal
from app.models import (CaseRecord, ClientProfile, RiskAssessmentDraft,
                        RiskFinding, Severity)
from app.report import (render_index, render_playbook, render_report,
                        render_review)


PROFILE = ClientProfile(
    business_name="Northstar Foods", industry="restaurant", employees=12,
    covers_requested=["Fire"], summary="Restaurant with a gas kitchen.",
)
FINDING = RiskFinding(
    factor_name="uncertified_gas", section="Fire", severity=Severity.high,
    suggested_points=18, evidence_quote="Gas certificate: Missing",
    reasoning="The installation has no current certificate.",
    precedent_case_ids=["C-0001"], playbook_rule_ids=["PB-001"], confidence=.93,
)


def test_review_workspace_renders_source_live_score_and_audit_links():
    draft = RiskAssessmentDraft(client_profile=PROFILE, findings=[FINDING])
    result = GuardrailResult(findings=[FINDING], score=18, band="Moderate")

    html = render_review(
        "draft-1", draft, result, "fake", "2026-08-07 10:00",
        "Business: Northstar Foods\nGas certificate: Missing",
    )

    assert 'id="source-document"' in html
    assert 'id="live-score">18' in html
    assert 'href="/cases/C-0001"' in html
    assert 'href="/playbook#PB-001"' in html
    assert 'name="new_evidence_quote"' in html


def test_report_renders_human_gated_learning_proposal():
    case = CaseRecord(
        case_id="C-0002", created_at="2026-08-07T10:00:00", source="assessment",
        client_profile=PROFILE, summary=PROFILE.summary,
        draft_findings=[FINDING], approved_findings=[FINDING],
        final_score=18, final_band="Moderate",
    )
    proposal = LearningProposal(
        case_id=case.case_id, current_playbook="# Underwriting Playbook\n",
        proposed_playbook="# Underwriting Playbook\n\n## PB-001 · Gas\nTreat as high.\n",
        change_note="Added gas rule.",
    )

    html = render_report(case, "fake", "2026-08-07 10:00", learning_proposal=proposal)

    assert 'action="/learning/C-0002"' in html
    assert 'value="accept"' in html
    assert 'value="skip"' in html
    assert "Nothing enters the underwriting playbook until you approve it" in html


def test_dashboard_and_playbook_render_enterprise_demo_elements():
    dashboard = render_index("Sample application", case_count=3, rule_count=2)
    playbook = render_playbook(
        "# Underwriting Playbook\n\n## PB-001 · Gas certification\nTreat missing certificates as high.\n"
    )

    assert "Recommended demo journey" in dashboard
    assert "Converge Underwriting" in dashboard
    assert '/static/converge-mark.svg' in dashboard
    assert "3</div><div class=\"metric-label\">Approved precedents" in dashboard
    assert 'id="PB-001"' in playbook
    assert "Gas certification" in playbook
