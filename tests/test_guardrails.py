"""Guardrails are the auditable core — these tests prove an underwriter can
trust the deterministic layer regardless of what the LLM proposes."""

import json
from pathlib import Path

import pytest

from app.guardrails import (apply, band_for_findings, band_for_score,
                            config_dir, evidence_is_present, load_scoring_config,
                            load_severity_points, load_thresholds,
                            quote_is_substantial, score_findings)
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


def test_band_is_equal_weight_mean_of_severity_points():
    low = _finding(severity=Severity.low)
    medium = _finding(severity=Severity.medium)
    high = _finding(severity=Severity.high)
    severe = _finding(severity=Severity.severe)
    assert band_for_findings([]) == "Low"
    assert score_findings([]).risk_score == 0.0
    assert band_for_findings([low, low]) == "Low"
    assert score_findings([low, low]).risk_score == 12.5
    assert band_for_findings([medium]) == "Moderate"
    assert score_findings([medium]).risk_score == 37.5
    assert band_for_findings([high]) == "Elevated"
    assert score_findings([high]).risk_score == 62.5
    # Three medium findings average to 37.5 → Moderate (not the old count rule).
    assert band_for_findings([medium, medium, medium]) == "Moderate"
    assert band_for_findings([severe]) == "High"
    assert score_findings([severe]).risk_score == 87.5
    # Three high findings average to 62.5 → Elevated.
    assert band_for_findings([high, high, high]) == "Elevated"
    mixed = score_findings([low, severe])
    assert mixed.risk_score == 50.0  # (12.5 + 87.5) / 2
    assert mixed.band == "Elevated"
    assert "12.5" in mixed.explanation and "87.5" in mixed.explanation


def test_score_threshold_boundaries():
    assert band_for_score(0.0) == "Low"
    assert band_for_score(24.99) == "Low"
    assert band_for_score(25.0) == "Moderate"
    assert band_for_score(49.99) == "Moderate"
    assert band_for_score(50.0) == "Elevated"
    assert band_for_score(74.99) == "Elevated"
    assert band_for_score(75.0) == "High"
    assert band_for_score(100.0) == "High"


def test_severe_finding_triggers_referral():
    result = apply(_draft(_finding(severity=Severity.severe)), DOC)
    assert result.band == "High"
    assert result.risk_score == 87.5
    assert any("Severe finding" in r for r in result.referrals)


def test_novel_finding_triggers_referral():
    novel = _finding(precedent_case_ids=[])
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
    draft = _draft(_finding(precedent_case_ids=["C-9999"]))
    draft._retrieved_case_ids = {"C-0001"}

    result = apply(draft, DOC)

    assert result.findings[0].precedent_case_ids == []
    assert len(result.invalid_citations) == 1
    assert any("Unverified audit" in referral for referral in result.referrals)
    assert any("NOVEL" in referral for referral in result.referrals)


def _write_thresholds(rows: dict) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "severity_points.json").write_text(
        json.dumps({"thresholds": rows}), encoding="utf-8")


def test_a_threshold_gap_is_rejected_instead_of_silently_banding_high():
    """A score in an uncovered range matched no row and fell through onto High —
    the most expensive loading — with nothing on screen to show the config was
    wrong. A tuning typo must fail loudly instead."""
    _write_thresholds({"Low": [0, 20], "Moderate": [25, 50],
                       "Elevated": [50, 75], "High": [75, 100]})
    # low + low + medium averages 20.83, which lands in the uncovered 20–25 gap.
    bucket = [_finding(severity=Severity.low), _finding(severity=Severity.low),
              _finding(severity=Severity.medium)]

    with pytest.raises(ValueError) as raised:
        score_findings(bucket)

    assert "gap" in str(raised.value)


def test_overlapping_or_short_threshold_rows_are_rejected():
    _write_thresholds({"Low": [0, 30], "Moderate": [25, 50],
                       "Elevated": [50, 75], "High": [75, 100]})
    with pytest.raises(ValueError) as overlapping:
        load_thresholds()
    assert "overlap" in str(overlapping.value)

    _write_thresholds({"Low": [0, 25], "Moderate": [25, 50],
                       "Elevated": [50, 75], "High": [75, 90]})
    with pytest.raises(ValueError) as short:
        load_thresholds()
    assert "0–100" in str(short.value)

    _write_thresholds({"Low": [0, 25], "Moderate": [25, 25],
                       "Elevated": [25, 75], "High": [75, 100]})
    with pytest.raises(ValueError) as empty:
        load_thresholds()
    assert "lo < hi" in str(empty.value)


def test_a_retuned_tiling_config_bands_by_its_own_cutoffs():
    _write_thresholds({"Low": [0, 20], "Moderate": [20, 45],
                       "Elevated": [45, 70], "High": [70, 100]})

    assert band_for_score(19.99) == "Low"
    assert band_for_score(22.5) == "Moderate"
    assert band_for_score(69.99) == "Elevated"
    assert band_for_score(70.0) == "High"
    assert band_for_findings([_finding(severity=Severity.high)]) == "Elevated"


def test_out_of_range_severity_points_are_rejected(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "severity_points.json").write_text(
        json.dumps({"points": {"low": 125}, "thresholds": {
            "Low": [0, 25], "Moderate": [25, 50], "Elevated": [50, 75], "High": [75, 100],
        }}),
        encoding="utf-8",
    )
    monkeypatch.setenv("UW_CONFIG_DIR", str(config))
    with pytest.raises(ValueError) as raised:
        load_severity_points()
    assert "points.low" in str(raised.value)


def test_shipped_severity_points_config_parses_cleanly(monkeypatch):
    """The git-tracked config must load under the same validation production uses."""
    shipped = Path(__file__).resolve().parents[1] / "config"
    monkeypatch.setenv("UW_CONFIG_DIR", str(shipped))
    points, thresholds = load_scoring_config()
    assert points["low"] == 12.5
    assert points["severe"] == 87.5
    assert thresholds[0] == ("Low", 0.0, 25.0)
    assert band_for_score(62.5, thresholds) == "Elevated"
