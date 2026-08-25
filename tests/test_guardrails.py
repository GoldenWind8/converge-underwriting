"""Guardrails are the auditable core — these tests prove an underwriter can
trust the deterministic layer regardless of what the LLM proposes."""

from app.guardrails import (apply, band_for_findings, evidence_is_present,
                            quote_is_substantial)
from app.models import (ClientProfile, RiskAssessmentDraft, RiskFinding,
                        Severity)
from app.sections import SectionId

DOC = (
    "Business name: Acme Co\n"
    "Fire cover: Yes\n"
    "Fire extinguishers: No\n"
    "Hazardous materials: Yes (paint thinners on site)\n"
    "Vehicles parked on the street overnight\n"
)


def _finding(**overrides) -> RiskFinding:
    base = dict(
        factor_name="no_fire_extinguishers",
        section=SectionId.fire,
        severity=Severity.high,
        evidence_quote="Fire extinguishers: No",
        reasoning="No first-response fire protection.",
        precedent_case_ids=["C-0001"],
        playbook_rule_ids=[],
        confidence=0.9,
    )
    base.update(overrides)
    return RiskFinding(**base)


def _draft(*findings) -> RiskAssessmentDraft:
    return RiskAssessmentDraft(client_profile=ClientProfile(), findings=list(findings))


def test_hallucinated_evidence_is_dropped():
    result = apply(_draft(_finding(evidence_quote="The building is made of straw")), DOC)
    assert result.findings == []
    assert len(result.dropped) == 1
    assert any("dropped" in r for r in result.referrals)


def test_evidence_matches_through_punctuation_and_case():
    result = apply(_draft(_finding(evidence_quote="fire extinguishers:  NO")), DOC)
    assert len(result.findings) == 1


def test_one_word_quotes_are_not_evidence():
    # §7.2: 'Yes' occurs in the document but proves nothing.
    result = apply(_draft(_finding(evidence_quote="Yes")), DOC)
    assert result.findings == []
    assert "too short or generic" in result.dropped[0][1]


def test_quote_substance_rules():
    assert not quote_is_substantial("Yes")
    assert not quote_is_substantial("no")
    assert not quote_is_substantial("yes and no yes the")  # stopwords only
    assert quote_is_substantial("Asbestos roof throughout")
    assert not evidence_is_present("Yes", DOC)
    assert evidence_is_present("Fire extinguishers: No", DOC)


def test_band_is_derived_from_the_severity_profile():
    low = _finding(severity=Severity.low)
    medium = _finding(severity=Severity.medium)
    high = _finding(severity=Severity.high)
    severe = _finding(severity=Severity.severe)
    assert band_for_findings([]) == "Low"
    assert band_for_findings([low, low]) == "Low"
    assert band_for_findings([medium]) == "Moderate"
    assert band_for_findings([high]) == "Elevated"
    assert band_for_findings([medium, medium, medium]) == "Elevated"
    assert band_for_findings([severe]) == "High"
    assert band_for_findings([high, high, high]) == "High"


def test_severe_finding_triggers_referral():
    result = apply(_draft(_finding(severity=Severity.severe)), DOC)
    assert result.band == "High"
    assert any("Severe finding" in r for r in result.referrals)


def test_novel_finding_triggers_referral():
    novel = _finding(precedent_case_ids=[], playbook_rule_ids=[])
    result = apply(_draft(novel), DOC)
    assert any("NOVEL" in r for r in result.referrals)


def test_low_confidence_triggers_referral():
    result = apply(_draft(_finding(confidence=0.3)), DOC)
    assert any("Low-confidence" in r for r in result.referrals)


def test_findings_sorted_by_section_order_then_severity():
    result = apply(_draft(
        _finding(factor_name="motor_low", section=SectionId.motor, severity=Severity.low,
                 evidence_quote="Vehicles parked on the street overnight"),
        _finding(factor_name="fire_high", section=SectionId.fire, severity=Severity.high),
        _finding(factor_name="fire_severe", section=SectionId.fire, severity=Severity.severe),
    ), DOC)
    assert [f.factor_name for f in result.findings] == ["fire_severe", "fire_high", "motor_low"]


def test_unverified_audit_citations_are_removed_and_referred():
    draft = _draft(_finding(
        precedent_case_ids=["C-9999"], playbook_rule_ids=["PB-999"]
    ))
    draft._retrieved_case_ids = {"C-0001"}
    draft._available_rule_ids = {"PB-001"}

    result = apply(draft, DOC)

    assert result.findings[0].precedent_case_ids == []
    assert result.findings[0].playbook_rule_ids == []
    assert len(result.invalid_citations) == 2
    assert any("Unverified audit" in referral for referral in result.referrals)
    assert any("NOVEL" in referral for referral in result.referrals)
