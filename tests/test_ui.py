from app.guardrails import GuardrailResult
from app.models import (CaseRecord, ClientProfile, Correction,
                        NeedsDetermination, Requirement, RiskAssessmentDraft,
                        RiskFinding, SectionNeed, Severity, SumInsured)
from app.needs import _repair
from app.report import (render_cases, render_index, render_needs,
                        render_pricing, render_rates, render_report,
                        render_review)
from app.sections import SectionId
from app import pricing


PROFILE = ClientProfile(
    business_name="Northstar Foods", industry="restaurant", employees=12,
    covers_requested=["Fire"], summary="Restaurant with a gas kitchen.",
)
FINDING = RiskFinding(
    factor_name="uncertified_gas", section=SectionId.fire, severity=Severity.high,
    assessment_note="Below standard for a food-production occupancy.",
    evidence_quote="Gas certificate: Missing",
    reasoning="The installation has no current certificate.",
    precedent_case_ids=["C-0001"], confidence=.93,
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
    assert 'class="card sticky-head"' in html, "column headings stay visible while scrolling"
    assert "Learn" not in html and "Review" not in html, "stepper is Submit · Needs · Price"


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

    assert 'action="/review/draft-1"' in html
    assert "Save &amp; go back" in html
    assert 'href="/drafts/draft-1/price"' in html, "the way back to the Price gate"
    assert 'id="source-document"' in html
    assert 'id="live-band"' in html
    assert "2. Fire" in html and "3. Business Interruption" in html
    assert 'href="/cases/C-0001"' in html
    assert "playbook" not in html.lower()
    assert 'name="new_evidence_quote"' in html
    assert 'name="note_0"' in html, "the why-note input must be on every finding"
    assert "3 model call(s)" in html
    assert "points" not in html.lower(), "no score anywhere on the review surface"
    assert html.count('<details class="section-block" open>') == 2, "one collapsible block per section"
    assert 'id="toggle-all"' in html
    assert "Uncertified gas" in html and 'class="mono">uncertified_gas' not in html, \
        "the screen shows plain English, never the snake_case factor id"


def _priced(findings):
    return pricing.price_case(NEEDS, findings, [SumInsured(section=SectionId.fire, amount=1_000_000, basis="Stock")])


def test_price_gate_lists_findings_with_editable_ratings_and_the_commit_bar():
    second = FINDING.model_copy(update={"factor_name": "open_flame_cooking", "assessment_note": "",
                                        "reasoning": "Open flames near stock. Further detail here."})
    html = render_pricing(_priced([FINDING, second]), [FINDING, second], "2026-09-12 10:00",
                          draft_id="draft-1", profile=PROFILE, usage={"calls": 2})

    assert 'action="/drafts/draft-1/price"' in html
    assert "Human gate 2" in html
    assert 'name="severity_0"' in html and 'name="severity_1"' in html, "one rating select per finding"
    assert "Uncertified gas" in html and "Open flame cooking" in html
    assert "Below standard for a food-production occupancy." in html
    assert "Open flames near stock." in html and "Further detail here" not in html, \
        "description is the first sentence of the reasoning when there is no note"
    assert 'name="checked_by"' in html and "required" in html
    assert 'name="add_to_memory" checked' in html
    assert "Approve &amp; price" in html
    assert 'href="/review/draft-1"' in html, "the drill-down link"
    assert "const LOADINGS=" in html, "band -> loading table is available to the live recalc"
    assert "Not stated" not in html and "Not priced" not in html
    assert "2 model call(s)" in html


def test_adjust_pricing_for_a_stored_case_keeps_ratings_read_only():
    case = CaseRecord(case_id="C-0007", created_at="2026-09-01T10:00:00", source="assessment",
                      client_profile=PROFILE, summary=PROFILE.summary, needs=NEEDS,
                      approved_findings=[FINDING], final_band="Elevated", checked_by="Lee",
                      pricing=_priced([FINDING]))
    html = render_pricing(case.pricing, case.approved_findings, "2026-09-12 10:00", case=case)

    assert 'action="/cases/C-0007/pricing"' in html
    assert "severity_0" not in html, "approved ratings are not edited from the pricing view"
    assert 'value="Lee"' in html
    assert "add_to_memory" not in html
    assert "Save pricing" in html


def test_report_is_the_insurer_document_quote_first():
    case = CaseRecord(
        case_id="C-0002", created_at="2026-08-07T10:00:00", source="assessment",
        client_profile=PROFILE, summary=PROFILE.summary, needs=NEEDS,
        draft_findings=[FINDING], approved_findings=[FINDING],
        corrections=[Correction(type="severity_changed", factor_name="uncertified_gas",
                                detail="medium -> high", note="Certificates are non-negotiable.")],
        final_band="Elevated", checked_by="Sashin",
        pricing=pricing.price_case(NEEDS + [SectionNeed(section=SectionId.theft, requirement=Requirement.required)],
                                   [FINDING], [SumInsured(section=SectionId.fire, amount=1_000_000)]),
    )

    html = render_report(case, "fake", "2026-08-07 10:00")

    assert "Prepared by Sashin" in html
    assert "Human approved" not in html
    assert html.index("Quote summary") < html.index("Itemised quote") < html.index("Risk assessment")
    assert "Needs determination" not in html and "Gas kitchen on site." not in html, "the needs table is gone"
    assert "Certificates are non-negotiable." not in html, "reviewer notes are internal"
    assert "Gas certificate: Missing" not in html, "evidence quotes are internal"
    assert "Theft" not in html.split("Quote summary")[1], "unpriced lines stay off the quote"
    assert 'action="/cases/C-0002/delete"' in html


def test_dashboard_renders_without_the_playbook():
    dashboard = render_index("Sample application", case_count=3)

    assert "Recommended demo journey" in dashboard
    assert "Converge Underwriting" in dashboard
    assert '/static/converge-mark.svg' in dashboard
    assert "3</div><div class=\"metric-label\">Approved precedents" in dashboard
    assert "playbook" not in dashboard.lower() and "Learn" not in dashboard


def test_factor_labels_are_humanised_with_optional_overrides(tmp_path):
    import json
    from app.report import _label

    assert _label("uncertified_gas_installation") == "Uncertified gas installation"

    (pricing.config_dir()).mkdir(parents=True, exist_ok=True)
    (pricing.config_dir() / "factor_labels.json").write_text(
        json.dumps({"uncertified_gas_installation": "Gas installation not certified"})
    )
    assert _label("uncertified_gas_installation") == "Gas installation not certified"
    assert _label("late_night_trading") == "Late night trading"


def test_rates_page_bolds_placeholders_and_offers_save_and_go_back():
    html = render_rates(pricing.load_rates(), pricing.load_loadings(), saved=True, back="/cases/C-0001/pricing")

    assert 'class="needs-confirm"' in html, "placeholder rates stand out until the broker confirms them"
    assert 'name="confirmed_motor"' in html and 'name="confirmed_fire"' not in html
    assert 'name="next" value="/cases/C-0001/pricing"' in html
    assert "Save &amp; go back" in html
    assert 'class="status-icon ok" title="Saved' in html, "status is an icon with hover text, not a text box"
    assert "<div class=\"notice\"" not in html


def test_case_memory_page_shows_status_icons_delete_forms_and_the_deleted_log():
    active = CaseRecord(case_id="C-0001", created_at="2026-09-01T10:00:00", source="assessment",
                        client_profile=PROFILE, summary=PROFILE.summary, approved_findings=[FINDING])
    pending = active.model_copy(update={"case_id": "C-0002", "source": "chat_ingestion", "provisional": True})
    gone = active.model_copy(update={"case_id": "C-0003", "deleted_at": "2026-09-10T09:00:00",
                                     "deleted_by": "Cameron", "deleted_reason": "Test data."})

    html = render_cases([active, pending], [gone])

    assert 'class="status-icon ok" title="Human approved 2026-09-01' in html
    assert 'class="status-icon warn" title="Provisional' in html
    assert html.count('action="/cases/C-0002/confirm"') == 1 and 'action="/cases/C-0001/confirm"' not in html
    assert 'action="/cases/C-0001/delete"' in html and 'name="reason"' in html
    assert "Deleted · 1 case(s)" in html
    assert "Cameron" in html and "Test data." in html and "2026-09-10 09:00:00" in html
    assert 'action="/cases/C-0003/delete"' not in html
