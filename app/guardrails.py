"""
Deterministic guardrails (docs/SOLUTION_DESIGN.md §4.3).

The LLM proposes findings; this module is what keeps the output defensible.
No LLM here — an underwriter can reproduce everything in this file by hand.

  1. Evidence check — a finding whose evidence_quote does not appear in the
     source document is DROPPED (kills hallucinated evidence).
  2. Point caps — suggested_points are clamped per severity tier.
  3. Band mapping — total score -> risk band, fixed thresholds.
  4. Referral triggers — low confidence, novel findings (no precedent and no
     playbook rule), and scores near a band boundary go to a human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

from .models import RiskAssessmentDraft, RiskFinding, Severity

POINT_CAPS = {
    Severity.info: 2,
    Severity.low: 6,
    Severity.medium: 12,
    Severity.high: 20,
}

# score >= threshold -> band (checked top-down)
BAND_THRESHOLDS = [(50, "High"), (30, "Elevated"), (15, "Moderate")]
BOUNDARY_MARGIN = 3  # within this of a threshold -> refer to a human
CONFIDENCE_FLOOR = 0.6


@dataclass
class GuardrailResult:
    findings: List[RiskFinding] = field(default_factory=list)
    dropped: List[Tuple[RiskFinding, str]] = field(default_factory=list)
    score: int = 0
    band: str = "Low"
    referrals: List[str] = field(default_factory=list)


def band_for_score(score: int) -> str:
    for threshold, band in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "Low"


def _normalise(text: str) -> str:
    """Lowercase and collapse everything non-alphanumeric, so an evidence quote
    still matches through punctuation/whitespace differences."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def apply(draft: RiskAssessmentDraft, raw_text: str) -> GuardrailResult:
    result = GuardrailResult()
    doc = _normalise(raw_text)

    for f in draft.findings:
        quote = _normalise(f.evidence_quote)
        if not quote or quote not in doc:
            result.dropped.append((f, "evidence quote not found verbatim in the source document"))
            continue
        cap = POINT_CAPS[f.severity]
        capped = max(0, min(f.suggested_points, cap))
        result.findings.append(f.model_copy(update={"suggested_points": capped}))

    result.findings.sort(key=lambda f: -f.suggested_points)
    result.score = sum(f.suggested_points for f in result.findings)
    result.band = band_for_score(result.score)

    low_conf = [f.factor_name for f in result.findings if f.confidence < CONFIDENCE_FLOOR]
    if low_conf:
        result.referrals.append(
            "Low-confidence finding(s) — human review required: " + ", ".join(low_conf) + "."
        )

    novel = [f.factor_name for f in result.findings
             if not f.precedent_case_ids and not f.playbook_rule_ids]
    if novel:
        result.referrals.append(
            "NOVEL finding(s) with no precedent case or playbook rule — human review required: "
            + ", ".join(novel) + "."
        )

    for threshold, _band in BAND_THRESHOLDS:
        if abs(result.score - threshold) <= BOUNDARY_MARGIN:
            result.referrals.append(
                f"Score {result.score} is within {BOUNDARY_MARGIN} points of the "
                f"{threshold}-point band boundary — human review required."
            )
            break

    if result.dropped:
        names = ", ".join(f.factor_name for f, _ in result.dropped)
        result.referrals.append(
            f"{len(result.dropped)} proposed finding(s) dropped for unverifiable evidence: {names}."
        )

    return result
