"""The deterministic pricing engine: premium = sum insured x rate x (1 + loading).
No LLM anywhere in this file's subject — every number must be reproducible by hand."""

import json
import os
from pathlib import Path

from app import pricing
from app.guardrails import band_for_findings, band_for_section
from app.models import Requirement, RiskFinding, SectionNeed, Severity, SumInsured
from app.sections import SectionId


def _finding(section, severity):
    return RiskFinding(
        factor_name=f"factor_{severity.value}", section=section, severity=severity,
        evidence_quote="stated in the submission text", reasoning="test", confidence=0.9,
    )


def _need(section):
    return SectionNeed(section=section, requirement=Requirement.required, reason="test")


def test_band_for_section_is_the_case_rule_scoped_to_one_section():
    findings = [_finding(SectionId.fire, Severity.severe)]
    assert band_for_section(findings) == band_for_findings(findings) == "High"
    assert band_for_section([]) == "Low"
    assert band_for_section([_finding(SectionId.fire, Severity.medium)]) == "Moderate"


def test_price_case_computes_base_and_adjusted_premiums():
    pricing.save_rates({**pricing.DEFAULT_RATES, "fire": {"rate": 0.40, "basis": "x"}})
    pricing.save_loadings({"Low": -10, "Moderate": 0, "Elevated": 10, "High": 25})

    result = pricing.price_case(
        needs=[_need(SectionId.fire), _need(SectionId.accounts_receivable)],
        findings=[_finding(SectionId.fire, Severity.severe),
                  _finding(SectionId.accounts_receivable, Severity.low)],
        sums=[SumInsured(section=SectionId.fire, amount=18_000_000, basis="Plant + stock"),
              SumInsured(section=SectionId.accounts_receivable, amount=2_000_000)],
    )

    fire = next(l for l in result.lines if l.section == SectionId.fire)
    assert fire.band == "High"
    assert fire.base_premium == 72_000            # 18m x 0.40%
    assert fire.applied_loading == fire.table_loading == 25
    assert fire.adjusted_premium == 90_000        # loaded +25%
    assert not fire.overridden

    ar = next(l for l in result.lines if l.section == SectionId.accounts_receivable)
    assert ar.band == "Low"
    assert ar.base_premium == 6_000               # 2m x 0.30%
    assert ar.adjusted_premium == 5_400           # discounted -10%

    assert result.base_total == 78_000
    assert result.adjusted_total == 95_400


def test_required_section_without_sum_insured_is_not_priced():
    result = pricing.price_case(
        needs=[_need(SectionId.fidelity)],
        findings=[_finding(SectionId.fidelity, Severity.high)],
        sums=[SumInsured(section=SectionId.fidelity, amount=None)],
    )
    line = result.lines[0]
    assert line.band == "Elevated"
    assert line.base_premium is None and line.adjusted_premium is None
    assert result.base_total == 0 and result.adjusted_total == 0


def test_only_required_sections_are_priced():
    needs = [
        _need(SectionId.fire),
        SectionNeed(section=SectionId.glass, requirement=Requirement.not_applicable, reason="none"),
    ]
    result = pricing.price_case(needs, [], [SumInsured(section=SectionId.fire, amount=1_000_000)])
    assert [l.section for l in result.lines] == [SectionId.fire]


def test_manual_override_is_applied_and_disclosed():
    result = pricing.price_case(
        needs=[_need(SectionId.fire)],
        findings=[],  # no findings -> Low band -> table -10
        sums=[SumInsured(section=SectionId.fire, amount=1_000_000)],
        overrides={SectionId.fire: 15},
    )
    line = result.lines[0]
    assert line.table_loading == -10 and line.applied_loading == 15
    assert line.overridden
    assert line.adjusted_premium == round(line.base_premium * 1.15)

    # An "override" equal to the table value is not an override at all.
    same = pricing.price_case(
        needs=[_need(SectionId.fire)], findings=[],
        sums=[SumInsured(section=SectionId.fire, amount=1_000_000)],
        overrides={SectionId.fire: -10},
    )
    assert not same.lines[0].overridden


def test_config_files_are_created_with_placeholders_and_roundtrip():
    config_dir = Path(os.environ["UW_CONFIG_DIR"])
    assert not (config_dir / "rates.json").exists()

    rates = pricing.load_rates()
    loadings = pricing.load_loadings()
    assert (config_dir / "rates.json").exists() and (config_dir / "loadings.json").exists()
    assert {s.value for s in SectionId} <= set(rates)
    assert loadings == pricing.DEFAULT_LOADINGS

    rates["fire"]["rate"] = 0.99
    pricing.save_rates(rates)
    assert pricing.load_rates()["fire"]["rate"] == 0.99
    assert json.loads((config_dir / "rates.json").read_text())["fire"]["rate"] == 0.99


def test_edited_config_missing_a_section_falls_back_to_placeholder():
    rates = pricing.load_rates()
    rates.pop("umbrella-liability")
    pricing.save_rates(rates)
    assert pricing.load_rates()["umbrella-liability"] == pricing.DEFAULT_RATES["umbrella-liability"]
