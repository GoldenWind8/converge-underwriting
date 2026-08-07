"""Guardrails are the auditable core now — these tests prove an underwriter can
trust the deterministic layer regardless of what the LLM proposes."""

from app.guardrails import POINT_CAPS, apply, band_for_score
from app.models import ClientProfile, RiskAssessmentDraft, RiskFinding, Severity

DOC = (
    "Business name: Acme Co\n"
    "Fire cover: Yes\n"
    "Fire extinguishers: No\n"
    "Hazardous materials: Yes (paint thinners on site)\n"
)


def _finding(**overrides) -> RiskFinding:
    base = dict(
        factor_name="no_fire_extinguishers",
        section="Fire",
        severity=Severity.high,
        suggested_points=15,
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


def test_points_capped_per_severity():
    result = apply(_draft(_finding(suggested_points=99)), DOC)
    assert result.findings[0].suggested_points == POINT_CAPS[Severity.high]


def test_band_mapping():
    assert band_for_score(0) == "Low"
    assert band_for_score(15) == "Moderate"
    assert band_for_score(30) == "Elevated"
    assert band_for_score(50) == "High"


def test_novel_finding_triggers_referral():
    novel = _finding(precedent_case_ids=[], playbook_rule_ids=[])
    result = apply(_draft(novel), DOC)
    assert any("NOVEL" in r for r in result.referrals)


def test_low_confidence_triggers_referral():
    result = apply(_draft(_finding(confidence=0.3)), DOC)
    assert any("Low-confidence" in r for r in result.referrals)


def test_score_is_sum_of_kept_findings():
    a = _finding(suggested_points=15)
    b = _finding(factor_name="hazmat", suggested_points=99,
                 evidence_quote="Hazardous materials: Yes (paint thinners on site)")
    result = apply(_draft(a, b), DOC)
    assert result.score == 15 + POINT_CAPS[Severity.high]
