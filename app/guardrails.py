"""
Deterministic guardrails (docs/SOLUTION_DESIGN.md §4.3).

The LLM proposes findings; this module is what keeps the output defensible.
No LLM here — an underwriter can reproduce everything in this file by hand.

  1. Evidence check — a finding whose evidence_quote does not appear in the
     source document is DROPPED (kills hallucinated evidence). Quotes that are
     too short or made only of stopwords are also dropped: the word "Yes"
     appearing somewhere in a form is not evidence of anything.
  2. Citation allow-list — precedent/rule citations not actually supplied to
     the model are removed and referred.
  3. Band mapping — the severity profile -> referral band. Categorical only;
     there is deliberately no score anywhere in this system.
  4. Referral triggers — low confidence, novel findings, and severe findings
     go to a human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

from .models import (SEVERITY_ORDER, RiskAssessmentDraft, RiskFinding,
                     Severity)
from .sections import section

CONFIDENCE_FLOOR = 0.6

# Evidence quotes below this length (normalised), or made only of stopwords,
# are rejected: they prove the words exist, not that the finding is evidenced.
MIN_QUOTE_CHARS = 12
STOPWORDS = {
    "yes", "no", "none", "n/a", "na", "the", "a", "an", "and", "or", "of",
    "to", "in", "on", "at", "for", "is", "are", "was", "not", "with",
}

# Deterministic band rule, checked top-down. Reproducible by hand:
#   High      any severe finding, or three or more high
#   Elevated  any high finding, or three or more medium
#   Moderate  any medium finding
#   Low       otherwise
BAND_RULE_TEXT = (
    "High: any severe finding, or 3+ high. Elevated: any high, or 3+ medium. "
    "Moderate: any medium. Low: otherwise."
)


@dataclass
class GuardrailResult:
    findings: List[RiskFinding] = field(default_factory=list)
    dropped: List[Tuple[RiskFinding, str]] = field(default_factory=list)
    band: str = "Low"
    referrals: List[str] = field(default_factory=list)
    invalid_citations: List[str] = field(default_factory=list)


def band_for_findings(findings: List[RiskFinding]) -> str:
    counts = {s: 0 for s in Severity}
    for f in findings:
        counts[f.severity] += 1
    if counts[Severity.severe] >= 1 or counts[Severity.high] >= 3:
        return "High"
    if counts[Severity.high] >= 1 or counts[Severity.medium] >= 3:
        return "Elevated"
    if counts[Severity.medium] >= 1:
        return "Moderate"
    return "Low"


def band_for_section(findings: List[RiskFinding]) -> str:
    """Band for ONE cover section, from that section's findings only.

    This is the single seam for section rating: the pricing engine and every
    surface that shows a per-section band call this and nothing else, so a
    future refinement — e.g. crediting mitigation factors to offset a single
    worst finding — changes this function and nothing downstream of it.
    Today it applies the same deterministic count rule as the case band.
    """
    return band_for_findings(findings)


def _normalise(text: str) -> str:
    """Lowercase and collapse everything non-alphanumeric, so an evidence quote
    still matches through punctuation/whitespace differences."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def quote_is_substantial(quote: str) -> bool:
    """Reject quotes too short or too generic to evidence anything."""
    normalised = _normalise(quote)
    words = normalised.split()
    if len(normalised) < MIN_QUOTE_CHARS:
        return False
    return not all(w in STOPWORDS for w in words)


def evidence_is_present(quote: str, raw_text: str) -> bool:
    """Return whether a substantial evidence quote occurs in the source text."""
    normalised_quote = _normalise(quote)
    return bool(
        quote_is_substantial(quote)
        and normalised_quote in _normalise(raw_text)
    )


def apply(draft: RiskAssessmentDraft, raw_text: str) -> GuardrailResult:
    result = GuardrailResult()
    doc = _normalise(raw_text)

    for f in draft.findings:
        quote = _normalise(f.evidence_quote)
        if not quote or quote not in doc:
            result.dropped.append((f, "evidence quote not found verbatim in the source document"))
            continue
        if not quote_is_substantial(f.evidence_quote):
            result.dropped.append((f, "evidence quote too short or generic to evidence a finding"))
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
        result.findings.append(f.model_copy(update={
            "precedent_case_ids": precedent_ids,
            "playbook_rule_ids": rule_ids,
        }))

    # Section order first (as the needs analysis lists them), worst first within.
    result.findings.sort(key=lambda f: (section(f.section).number, -SEVERITY_ORDER[f.severity]))
    result.band = band_for_findings(result.findings)

    severe = [f.factor_name for f in result.findings if f.severity == Severity.severe]
    if severe:
        result.referrals.append(
            "Severe finding(s) — human review required: " + ", ".join(severe) + "."
        )

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

    if result.dropped:
        names = ", ".join(f.factor_name for f, _ in result.dropped)
        result.referrals.append(
            f"{len(result.dropped)} proposed finding(s) dropped for unverifiable evidence: {names}."
        )

    return result
