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
    invalid_citations: List[str] = field(default_factory=list)


def band_for_score(score: int) -> str:
    for threshold, band in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "Low"


def _normalise(text: str) -> str:
    """Lowercase and collapse everything non-alphanumeric, so an evidence quote
    still matches through punctuation/whitespace differences."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def evidence_is_present(quote: str, raw_text: str) -> bool:
    """Return whether a non-empty evidence quote occurs in the source text."""
    normalised_quote = _normalise(quote)
    return bool(normalised_quote and normalised_quote in _normalise(raw_text))


def apply(draft: RiskAssessmentDraft, raw_text: str) -> GuardrailResult:
    result = GuardrailResult()
    doc = _normalise(raw_text)

    for f in draft.findings:
        quote = _normalise(f.evidence_quote)
        if not quote or quote not in doc:
            result.dropped.append((f, "evidence quote not found verbatim in the source document"))
            continue
        precedent_ids = f.precedent_case_ids
        rule_ids = f.playbook_rule_ids
        if draft._retrieved_case_ids is not None:
            invalid = [cid for cid in precedent_ids if cid not in draft._retrieved_case_ids]
            result.invalid_citations.extend(f"{f.factor_name}: unknown precedent {cid}" for cid in invalid)
            precedent_ids = [cid for cid in precedent_ids if cid in draft._retrieved_case_ids]
        if draft._available_rule_ids is not None:
            available_rules = {rid.upper() for rid in draft._available_rule_ids}
            invalid = [rid for rid in rule_ids if rid.upper() not in available_rules]
            result.invalid_citations.extend(f"{f.factor_name}: unknown rule {rid}" for rid in invalid)
            rule_ids = [rid.upper() for rid in rule_ids if rid.upper() in available_rules]
        cap = POINT_CAPS[f.severity]
        capped = max(0, min(f.suggested_points, cap))
        result.findings.append(f.model_copy(update={
            "suggested_points": capped,
            "precedent_case_ids": precedent_ids,
            "playbook_rule_ids": rule_ids,
        }))

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

    if result.invalid_citations:
        result.referrals.append(
            "Unverified audit citation(s) were removed — human review required: "
            + "; ".join(result.invalid_citations) + "."
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
