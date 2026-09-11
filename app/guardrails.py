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
  3. Risk score + band — each finding maps to points from its severity
     (config/severity_points.json); the bucket score is the equal-weight mean;
     the band is a threshold lookup over that mean (0–100).
  4. Referral triggers — low confidence, novel findings, and severe findings
     go to a human.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

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

# Defaults mirror config/severity_points.json — midpoints of each display band.
DEFAULT_SEVERITY_POINTS: Dict[str, float] = {
    "low": 12.5,
    "medium": 37.5,
    "high": 62.5,
    "severe": 87.5,
}

# Half-open [lo, hi) except High includes 100.
DEFAULT_THRESHOLDS: List[Tuple[str, float, float]] = [
    ("Low", 0.0, 25.0),
    ("Moderate", 25.0, 50.0),
    ("Elevated", 50.0, 75.0),
    ("High", 75.0, 100.0),
]

BAND_RULE_TEXT = (
    "Equal-weight mean of severity points (low=12.5, medium=37.5, high=62.5, "
    "severe=87.5); Low [0,25), Moderate [25,50), Elevated [50,75), High [75,100]."
)


@dataclass
class ScoreBreakdown:
    """Hand-reproducible working for one risk bucket (section or whole case)."""

    risk_score: float
    band: str
    finding_points: List[Tuple[str, str, float]] = field(default_factory=list)
    explanation: str = ""


@dataclass
class GuardrailResult:
    findings: List[RiskFinding] = field(default_factory=list)
    dropped: List[Tuple[RiskFinding, str]] = field(default_factory=list)
    band: str = "Low"
    risk_score: float = 0.0
    score_explanation: str = ""
    referrals: List[str] = field(default_factory=list)
    invalid_citations: List[str] = field(default_factory=list)


def _config_dir() -> Path:
    return Path(os.environ.get("UW_CONFIG_DIR", Path(__file__).resolve().parent.parent / "config"))


def load_severity_points() -> Dict[str, float]:
    """Severity → points map. Missing keys fall back to the documented defaults."""
    path = _config_dir() / "severity_points.json"
    points = dict(DEFAULT_SEVERITY_POINTS)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        for key, value in (raw.get("points") or {}).items():
            points[str(key)] = float(value)
    return points


def load_thresholds() -> List[Tuple[str, float, float]]:
    """Ordered (band, lo, hi) rows. High is inclusive of 100."""
    path = _config_dir() / "severity_points.json"
    if not path.exists():
        return list(DEFAULT_THRESHOLDS)
    raw = json.loads(path.read_text(encoding="utf-8"))
    thresholds = raw.get("thresholds") or {}
    if not thresholds:
        return list(DEFAULT_THRESHOLDS)
    order = ["Low", "Moderate", "Elevated", "High"]
    rows: List[Tuple[str, float, float]] = []
    for band in order:
        pair = thresholds.get(band)
        if pair is None or len(pair) != 2:
            raise ValueError(f"severity_points.json thresholds.{band} must be [lo, hi]")
        rows.append((band, float(pair[0]), float(pair[1])))
    return rows


def points_for_severity(severity: Severity, points: Dict[str, float] | None = None) -> float:
    table = points or load_severity_points()
    return float(table[severity.value])


def band_for_score(score: float, thresholds: List[Tuple[str, float, float]] | None = None) -> str:
    """Map a 0–100 score onto Low / Moderate / Elevated / High."""
    rows = thresholds or load_thresholds()
    s = float(score)
    for band, lo, hi in rows:
        if band == "High":
            if lo <= s <= hi:
                return band
        elif lo <= s < hi:
            return band
    if s < 0:
        return "Low"
    return "High"


def score_findings(findings: List[RiskFinding]) -> ScoreBreakdown:
    """Equal-weight mean of severity points → band. Empty bucket scores 0 (Low)."""
    points_table = load_severity_points()
    thresholds = load_thresholds()
    finding_points: List[Tuple[str, str, float]] = []
    for f in findings:
        pts = points_for_severity(f.severity, points_table)
        finding_points.append((f.factor_name, f.severity.value, pts))

    if not finding_points:
        explanation = (
            "No findings in this bucket — score 0.00 → Low "
            "(empty buckets are not priced as risk)."
        )
        return ScoreBreakdown(risk_score=0.0, band="Low", finding_points=[], explanation=explanation)

    total = sum(pts for _, _, pts in finding_points)
    n = len(finding_points)
    mean = total / n
    band = band_for_score(mean, thresholds)
    parts = "; ".join(
        f"{name} ({sev} → {pts:g})" for name, sev, pts in finding_points
    )
    explanation = (
        f"Equal-weight mean of {n} finding(s): ({parts}) "
        f"= {total:g} / {n} = {mean:.2f} → {band}."
    )
    return ScoreBreakdown(
        risk_score=mean,
        band=band,
        finding_points=finding_points,
        explanation=explanation,
    )


def band_for_findings(findings: List[RiskFinding]) -> str:
    return score_findings(findings).band


def score_for_findings(findings: List[RiskFinding]) -> float:
    return score_findings(findings).risk_score


def band_for_section(findings: List[RiskFinding]) -> str:
    """Band for ONE cover section, from that section's findings only.

    This is the single seam for section rating: the pricing engine and every
    surface that shows a per-section band call this and nothing else, so a
    future refinement — e.g. crediting mitigation factors to offset a single
    worst finding — changes this function and nothing downstream of it.
    """
    return score_findings(findings).band


def score_for_section(findings: List[RiskFinding]) -> float:
    return score_findings(findings).risk_score


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
    scored = score_findings(result.findings)
    result.band = scored.band
    result.risk_score = scored.risk_score
    result.score_explanation = scored.explanation

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
