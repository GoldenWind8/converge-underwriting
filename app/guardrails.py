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

# The severity → points map and the ordered band rows, always parsed together.
ScoringConfig = Tuple[Dict[str, float], List[Tuple[str, float, float]]]


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


def config_dir() -> Path:
    """The one definition of where the git-tracked, human-editable config files
    live. pricing.py reads its rate and loading tables from the same directory."""
    return Path(os.environ.get("UW_CONFIG_DIR", Path(__file__).resolve().parent.parent / "config"))


def _read_scoring_config() -> dict:
    path = config_dir() / "severity_points.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _points_from(raw: dict) -> Dict[str, float]:
    points = dict(DEFAULT_SEVERITY_POINTS)
    for key, value in (raw.get("points") or {}).items():
        points[str(key)] = float(value)
    for key, value in points.items():
        if not 0.0 <= value <= 100.0:
            raise ValueError(
                f"severity_points.json points.{key} must be in [0, 100], got {value:g}"
            )
    return points


def _validate_threshold_rows(rows: List[Tuple[str, float, float]]) -> None:
    """The bands must tile [0, 100] with no gap and no overlap.

    An uncovered score matches no row, and band_for_score falls through onto
    High — the most expensive loading in config/loadings.json. A tuning typo
    must fail loudly here rather than silently reprice a section.
    """
    for band, lo, hi in rows:
        if not lo < hi:
            raise ValueError(
                f"severity_points.json thresholds.{band} must have lo < hi, got [{lo:g}, {hi:g}]"
            )
    if rows[0][1] != 0.0 or rows[-1][2] != 100.0:
        raise ValueError(
            "severity_points.json thresholds must span the whole 0–100 score range, got "
            f"[{rows[0][1]:g}, {rows[-1][2]:g}]"
        )
    for (lower, _, lower_hi), (upper, upper_lo, _) in zip(rows, rows[1:]):
        if lower_hi != upper_lo:
            gap = "gap" if lower_hi < upper_lo else "overlap"
            raise ValueError(
                f"severity_points.json thresholds leave a {gap} between {lower} "
                f"(ends {lower_hi:g}) and {upper} (starts {upper_lo:g})"
            )


def _thresholds_from(raw: dict) -> List[Tuple[str, float, float]]:
    thresholds = raw.get("thresholds") or {}
    if not thresholds:
        return list(DEFAULT_THRESHOLDS)
    rows: List[Tuple[str, float, float]] = []
    for band, _, _ in DEFAULT_THRESHOLDS:
        pair = thresholds.get(band)
        if pair is None or len(pair) != 2:
            raise ValueError(f"severity_points.json thresholds.{band} must be [lo, hi]")
        rows.append((band, float(pair[0]), float(pair[1])))
    _validate_threshold_rows(rows)
    return rows


def load_scoring_config() -> ScoringConfig:
    """Points map + ordered (band, lo, hi) rows from ONE parse of the config.

    Scoring always needs both halves together, so every caller that bands a
    score should take them from here rather than re-reading the file twice.
    """
    raw = _read_scoring_config()
    return _points_from(raw), _thresholds_from(raw)


def load_severity_points() -> Dict[str, float]:
    """Severity → points map. Missing keys fall back to the documented defaults."""
    return _points_from(_read_scoring_config())


def load_thresholds() -> List[Tuple[str, float, float]]:
    """Ordered (band, lo, hi) rows. High is inclusive of 100."""
    return _thresholds_from(_read_scoring_config())


def band_rule_text(
    points: Dict[str, float] | None = None,
    thresholds: List[Tuple[str, float, float]] | None = None,
) -> str:
    """The banding rule in one sentence, built from the live config so it can
    never state numbers other than the ones actually scored with."""
    if points is None or thresholds is None:
        loaded_points, loaded_thresholds = load_scoring_config()
        points = points if points is not None else loaded_points
        thresholds = thresholds if thresholds is not None else loaded_thresholds
    pairs = ", ".join(
        f"{s.value}={points[s.value]:g}"
        for s in sorted(SEVERITY_ORDER, key=SEVERITY_ORDER.__getitem__)
    )
    bands = ", ".join(
        f"{band} [{lo:g},{hi:g}]" if band == "High" else f"{band} [{lo:g},{hi:g})"
        for band, lo, hi in thresholds
    )
    return f"Equal-weight mean of severity points ({pairs}); {bands}."


def points_for_severity(severity: Severity, points: Dict[str, float] | None = None) -> float:
    table = points or load_severity_points()
    return float(table[severity.value])


def band_for_score(score: float, thresholds: List[Tuple[str, float, float]] | None = None) -> str:
    """Map a 0–100 score onto Low / Moderate / Elevated / High."""
    rows = thresholds or load_thresholds()
    s = float(score)
    if s < 0 or s > 100:
        raise ValueError(f"risk score must be in [0, 100], got {s:g}")
    for band, lo, hi in rows:
        if band == "High":
            if lo <= s <= hi:
                return band
        elif lo <= s < hi:
            return band
    raise ValueError(
        f"risk score {s:g} matches no band in the configured thresholds "
        f"(expected a contiguous cover of [0, 100])"
    )


def score_findings(findings: List[RiskFinding], config: ScoringConfig | None = None) -> ScoreBreakdown:
    """Equal-weight mean of severity points → band. Empty bucket scores 0 (Low).

    Pass `config` to score many buckets against a single parse of the config
    file, as the pricing engine does across a case's cover sections.
    """
    points_table, thresholds = config if config is not None else load_scoring_config()
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


def score_section(findings: List[RiskFinding], config: ScoringConfig | None = None) -> ScoreBreakdown:
    """Score ONE cover section, from that section's findings only.

    This is the single seam for section rating: the pricing engine and every
    surface that shows a per-section band or score call this and nothing else,
    so a future refinement — e.g. crediting mitigation factors to offset a
    single worst finding — changes this function and nothing downstream of it.
    """
    return score_findings(findings, config)


def band_for_section(findings: List[RiskFinding]) -> str:
    return score_section(findings).band


def score_for_section(findings: List[RiskFinding]) -> float:
    return score_section(findings).risk_score


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
