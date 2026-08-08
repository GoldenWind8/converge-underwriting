"""
Cross-section driver roll-up. Deterministic — no model call.

The point: a section-by-section read hides one weakness in the business
surfacing under several cover sections at once. Findings carry driver slugs;
this groups them and keeps only drivers touching two or more sections,
most-cross-cutting first.
"""

from __future__ import annotations

from typing import List

from .models import SEVERITY_ORDER, DriverGroup, RiskFinding, Severity

# A driver hitting this many sections at medium-or-above is itself a referral.
REFERRAL_SECTION_COUNT = 3


def group_drivers(findings: List[RiskFinding]) -> List[DriverGroup]:
    by_driver: dict[str, List[DriverGroup.Hit]] = {}
    for f in findings:
        for driver in f.drivers:
            by_driver.setdefault(driver, []).append(
                DriverGroup.Hit(section=f.section, factor_name=f.factor_name, severity=f.severity)
            )
    groups = [
        DriverGroup(driver=driver, hits=hits, section_count=len({h.section for h in hits}))
        for driver, hits in by_driver.items()
    ]
    return sorted(
        (g for g in groups if g.section_count >= 2),
        key=lambda g: (-g.section_count, g.driver),
    )


def referral_drivers(groups: List[DriverGroup]) -> List[DriverGroup]:
    """Drivers that hit REFERRAL_SECTION_COUNT+ sections at medium or above."""
    flagged = []
    for group in groups:
        serious = {h.section for h in group.hits
                   if SEVERITY_ORDER[h.severity] >= SEVERITY_ORDER[Severity.medium]}
        if len(serious) >= REFERRAL_SECTION_COUNT:
            flagged.append(group)
    return flagged
