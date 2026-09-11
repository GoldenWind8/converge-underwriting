import json
import os
import re
from pathlib import Path

from app.guardrails import (GuardrailResult, band_rule_text,
                            load_scoring_config, score_findings)
from app.memory import LearningProposal
from app.models import (CasePricing, CaseRecord, ClientProfile, Correction,
                        NeedsDetermination, PricedSection, Requirement,
                        RiskAssessmentDraft, RiskFinding, SectionNeed, Severity)
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


def _injected(html: str, name: str):
    """The JSON constant the review page hands to its client-side recalc."""
    match = re.search(rf"const {name} = (.+?);\n", html)
    assert match, f"{name} is not injected into the review page"
    return json.loads(match.group(1))


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
    result = GuardrailResult(findings=[FINDING, second], band="Elevated", risk_score=62.5,
                             score_explanation="test")

    html = render_review(
        "draft-1", draft, result, "fake", "2026-08-07 10:00",
        "Business: Northstar Foods\nGas certificate: Missing",
        needs=NEEDS, usage={"calls": 3, "input_tokens": 10, "output_tokens": 5, "cost_usd": 0},
    )

    assert 'id="source-document"' in html
    assert 'id="live-band"' in html
    assert 'id="live-score"' in html
    assert "2. Fire" in html and "3. Business Interruption" in html
    assert 'href="/cases/C-0001"' in html
    assert 'href="/playbook#PB-001"' in html
    assert 'name="new_evidence_quote"' in html
    assert 'name="note_0"' in html, "the why-note input must be on every finding"
    assert "3 model call(s)" in html
    assert 'id="live-score">62.50</span>' in html, "the scored value itself must be rendered"
    assert band_rule_text() in html, "the surface states the rule it was scored by"


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


def test_review_recalc_is_handed_the_config_the_server_bands_with():
    """The in-page recalc must reach the same verdict /approve will store, so a
    tuned severity_points.json has to drive both sides, not just the server."""
    config_dir = Path(os.environ["UW_CONFIG_DIR"])
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "severity_points.json").write_text(json.dumps({
        "points": {"low": 4.0, "medium": 30.0, "high": 80.0, "severe": 96.0},
        "thresholds": {"Low": [0, 20], "Moderate": [20, 45],
                       "Elevated": [45, 70], "High": [70, 100]},
    }), encoding="utf-8")
    points, thresholds = load_scoring_config()
    scored = score_findings([FINDING])
    # The lone high finding is worth 80 under this config, which that config
    # bands High — under the defaults it would be 62.5 and only Elevated.
    assert (scored.risk_score, scored.band) == (80.0, "High")

    draft = RiskAssessmentDraft(client_profile=PROFILE, findings=[FINDING])
    html = render_review(
        "draft-2", draft,
        GuardrailResult(findings=[FINDING], band=scored.band,
                        risk_score=scored.risk_score,
                        score_explanation=scored.explanation),
        "fake", "2026-08-07 10:00", "Gas certificate: Missing", needs=NEEDS,
    )

    assert _injected(html, "SEVERITY_POINTS") == points
    assert [(r["band"], r["lo"], r["hi"])
            for r in _injected(html, "BAND_THRESHOLDS")] == thresholds
    assert 'id="live-score">80.00</span>' in html
    assert band_rule_text() in html
    assert "62.5" not in html, "no default point value may survive a tuned config"


def test_report_shows_the_section_score_behind_each_loading():
    """The header states a case score; each priced section states the score that
    picked its own loading, so the report explains every number it shows."""
    case = CaseRecord(
        case_id="C-0003", created_at="2026-08-07T10:00:00", source="assessment",
        client_profile=PROFILE, summary=PROFILE.summary, needs=NEEDS,
        draft_findings=[FINDING], approved_findings=[FINDING],
        final_band="Elevated", risk_score=62.5,
        pricing=CasePricing(
            lines=[PricedSection(section=SectionId.fire, band="Elevated", risk_score=62.5,
                                 rate=0.20, table_loading=10, applied_loading=10,
                                 sum_insured=1_000_000, base_premium=2_000,
                                 adjusted_premium=2_200)],
            base_total=2_000, adjusted_total=2_200,
        ),
    )

    html = render_report(case, "fake", "2026-08-07 10:00")

    assert "62.50 pts" in html
