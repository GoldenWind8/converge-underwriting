from app.guardrails import GuardrailResult
from app.memory import LearningProposal
from app.models import (CaseRecord, ClientProfile, Correction,
                        NeedsDetermination, Requirement, RiskAssessmentDraft,
                        RiskFinding, SectionNeed, Severity)
from app.needs import _repair
from app.report import (render_index, render_needs, render_playbook,
                        render_report, render_review)
from app.sections import SectionId


PROFILE = ClientProfile(
    business_name="Northstar Foods", industry="restaurant", employees=12,
    covers_requested=["Fire"], summary="Restaurant with a gas kitchen.",
)
FINDING = RiskFinding(
    factor_name="uncertified_gas", section=SectionId.fire, severity=Severity.high,
    assessment_note="Below standard for a food-production occupancy.",
    evidence_quote="Gas certificate: Missing",
    reasoning="The installation has no current certificate.",
    precedent_case_ids=["C-0001"], playbook_rule_ids=["PB-001"], confidence=.93,
)
NEEDS = _repair([SectionNeed(section=SectionId.fire, requirement=Requirement.required,
                             reason="Gas kitchen on site.")])


def test_needs_page_renders_all_sections_and_gate_one_controls():
    determination = NeedsDetermination(business_note="A restaurant.", needs=NEEDS)

    html = render_needs("needs-1", determination, PROFILE, "fake", "2026-08-08 10:00")

    assert 'action="/needs/needs-1"' in html
    assert html.count("requirement_") == 18
    assert 'name="motor_sub_type"' in html
    assert "Human gate 1" in html
    assert "A restaurant." in html


def test_review_workspace_renders_sections_and_why_note():
    second = FINDING.model_copy(update={
        "factor_name": "gas_bi_dependency", "section": SectionId.business_interruption,
    })
    draft = RiskAssessmentDraft(client_profile=PROFILE, findings=[FINDING, second])
    result = GuardrailResult(findings=[FINDING, second], band="Elevated")

    html = render_review(
        "draft-1", draft, result, "fake", "2026-08-07 10:00",
        "Business: Northstar Foods\nGas certificate: Missing",
        needs=NEEDS, usage={"calls": 3, "input_tokens": 10, "output_tokens": 5, "cost_usd": 0},
    )

    assert 'id="source-document"' in html
    assert 'id="live-band"' in html
    assert "2. Fire" in html and "3. Business Interruption" in html
    assert 'href="/cases/C-0001"' in html
    assert 'href="/playbook#PB-001"' in html
    assert 'name="new_evidence_quote"' in html
    assert 'name="note_0"' in html, "the why-note input must be on every finding"
    assert "3 model call(s)" in html
    assert "points" not in html.lower(), "no score anywhere on the review surface"


def test_report_renders_needs_rationale_and_reviewer_notes():
    case = CaseRecord(
        case_id="C-0002", created_at="2026-08-07T10:00:00", source="assessment",
        client_profile=PROFILE, summary=PROFILE.summary, needs=NEEDS,
        draft_findings=[FINDING], approved_findings=[FINDING],
        corrections=[Correction(type="severity_changed", factor_name="uncertified_gas",
                                detail="medium -> high", note="Certificates are non-negotiable.")],
        final_band="Elevated",
    )
    proposal = LearningProposal(
        case_id=case.case_id, current_playbook="# Underwriting Playbook\n",
        proposed_playbook="# Underwriting Playbook\n\n## PB-001 · [fire] Gas\nTreat as high.\n",
        change_note="Added gas rule.",
    )

    html = render_report(case, "fake", "2026-08-07 10:00", learning_proposal=proposal)

    assert 'action="/learning/C-0002"' in html
    assert 'value="accept"' in html and 'value="skip"' in html
    assert "Nothing enters the underwriting playbook until you approve it" in html
    assert "Needs determination" in html
    assert "Gas kitchen on site." in html
    assert "Certificates are non-negotiable." in html
    assert "Out of scope" not in html, "pricing is in scope now — deterministic, never LLM"
    assert "Premiums are deterministic" in html


def test_dashboard_and_playbook_render_enterprise_demo_elements():
    dashboard = render_index("Sample application", case_count=3, rule_count=2)
    playbook = render_playbook(
        "# Underwriting Playbook\n\n## PB-001 · [fire] Gas certification\nTreat missing certificates as high.\n"
    )

    assert "Recommended demo journey" in dashboard
    assert "Converge Underwriting" in dashboard
    assert '/static/converge-mark.svg' in dashboard
    assert "3</div><div class=\"metric-label\">Approved precedents" in dashboard
    assert 'id="PB-001"' in playbook
    assert "Gas certification" in playbook
