"""The cross-section driver roll-up: deterministic, and the compensating
mechanism for assessing sections in isolation."""

from app.drivers import group_drivers, referral_drivers
from app.models import RiskFinding, Severity
from app.sections import SectionId


def _finding(name, section, drivers, severity=Severity.medium):
    return RiskFinding(
        factor_name=name, section=section, severity=severity,
        evidence_quote="quoted from the submission", reasoning="r",
        drivers=drivers,
    )


def test_only_drivers_touching_two_or_more_sections_group():
    groups = group_drivers([
        _finding("a", SectionId.fire, ["combustible-stock", "no-sprinklers"]),
        _finding("b", SectionId.business_interruption, ["combustible-stock"]),
        _finding("c", SectionId.theft, ["no-cctv"]),
    ])
    assert [g.driver for g in groups] == ["combustible-stock"]
    assert groups[0].section_count == 2
    assert len(groups[0].hits) == 2


def test_two_findings_in_the_same_section_do_not_group():
    groups = group_drivers([
        _finding("a", SectionId.fire, ["no-sprinklers"]),
        _finding("b", SectionId.fire, ["no-sprinklers"]),
    ])
    assert groups == []


def test_most_cross_cutting_driver_first():
    groups = group_drivers([
        _finding("a", SectionId.fire, ["x", "y"]),
        _finding("b", SectionId.theft, ["x", "y"]),
        _finding("c", SectionId.money, ["y"]),
    ])
    assert [g.driver for g in groups] == ["y", "x"]


def test_referral_needs_three_sections_at_medium_or_above():
    groups = group_drivers([
        _finding("a", SectionId.fire, ["z"], Severity.medium),
        _finding("b", SectionId.theft, ["z"], Severity.high),
        _finding("c", SectionId.money, ["z"], Severity.low),  # low: does not count
    ])
    assert referral_drivers(groups) == []

    groups = group_drivers([
        _finding("a", SectionId.fire, ["z"], Severity.medium),
        _finding("b", SectionId.theft, ["z"], Severity.high),
        _finding("c", SectionId.money, ["z"], Severity.severe),
    ])
    assert [g.driver for g in referral_drivers(groups)] == ["z"]


def test_slugs_normalise_before_grouping():
    groups = group_drivers([
        _finding("a", SectionId.fire, ["No CCTV"]),
        _finding("b", SectionId.theft, ["no_cctv"]),
    ])
    assert [g.driver for g in groups] == ["no-cctv"]
