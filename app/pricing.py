"""
Deterministic pricing engine (the Price gate). No LLM here — like
guardrails.py, an underwriter can reproduce every number in this file by hand:

    premium = sum insured x rate x (1 + loading)

- Base rates are per cover section, flat regardless of sum insured, expressed
  as an annual percentage of the sum insured (config/rates.json).
- The loading is dictated by the section's risk band (config/loadings.json,
  one global table; negative values discount) and can be manually overridden
  per section at the Price gate. Overrides are disclosed, never silent.
- Only sections the broker confirmed as required are priced, and only when a
  broker-confirmed sum insured exists — a missing figure means "not priced",
  never a guess.

Both config files are git-tracked, human-editable on the Rates page, and
created with placeholder values on first use. The placeholder rates are
stand-ins until the broker's rate sheet arrives.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from .guardrails import band_for_section
from .models import (CasePricing, PricedSection, Requirement, RiskFinding,
                     SectionNeed, SumInsured)
from .sections import SectionId, section

BANDS = ["Low", "Moderate", "Elevated", "High"]

# Placeholder base rates: annual % of sum insured, flat per section.
# "basis" says what figure the rate applies to — shown on the Rates page.
DEFAULT_RATES: Dict[str, dict] = {
    "buildings-combined": {"rate": 0.15, "basis": "Building value"},
    "fire": {"rate": 0.40, "basis": "Plant, stock and contents"},
    "business-interruption": {"rate": 0.35, "basis": "Gross profit"},
    "office-contents": {"rate": 0.50, "basis": "Contents value"},
    "glass": {"rate": 1.00, "basis": "Replacement value"},
    "accounts-receivable": {"rate": 0.30, "basis": "Debtors outstanding"},
    "fidelity": {"rate": 0.50, "basis": "Limit of indemnity"},
    "theft": {"rate": 1.50, "basis": "Stock at risk"},
    "money": {"rate": 2.00, "basis": "Maximum cash on premises"},
    "goods-in-transit": {"rate": 1.00, "basis": "Maximum load per vehicle"},
    "electronic-equipment": {"rate": 1.20, "basis": "Equipment value"},
    "business-all-risks": {"rate": 2.50, "basis": "Portable items value"},
    "group-personal-accident": {"rate": 0.80, "basis": "Aggregate benefit"},
    "motor": {"rate": 4.00, "basis": "Fleet value"},
    "motor-traders": {"rate": 3.00, "basis": "Vehicles in custody"},
    "public-liability": {"rate": 0.10, "basis": "Limit of indemnity"},
    "broadform-liability": {"rate": 0.12, "basis": "Limit of indemnity"},
    "umbrella-liability": {"rate": 0.05, "basis": "Limit of indemnity"},
}

DEFAULT_LOADINGS: Dict[str, float] = {
    "Low": -10.0,
    "Moderate": 0.0,
    "Elevated": 10.0,
    "High": 25.0,
}


def _config_dir() -> Path:
    return Path(os.environ.get("UW_CONFIG_DIR", Path(__file__).resolve().parent.parent / "config"))


def _load(filename: str, defaults: dict) -> dict:
    """Read a config file, creating it with the defaults on first use."""
    path = _config_dir() / filename
    if not path.exists():
        _save(filename, defaults)
        return json.loads(json.dumps(defaults))
    return json.loads(path.read_text(encoding="utf-8"))


def _save(filename: str, payload: dict) -> None:
    path = _config_dir() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_rates() -> Dict[str, dict]:
    rates = _load("rates.json", DEFAULT_RATES)
    # A section missing from an edited file falls back to its placeholder,
    # so a config edit can never leave a section unpriceable.
    for section_id, entry in DEFAULT_RATES.items():
        rates.setdefault(section_id, dict(entry))
    return rates


def save_rates(rates: Dict[str, dict]) -> None:
    _save("rates.json", rates)


def load_loadings() -> Dict[str, float]:
    loadings = _load("loadings.json", DEFAULT_LOADINGS)
    for band, value in DEFAULT_LOADINGS.items():
        loadings.setdefault(band, value)
    return loadings


def save_loadings(loadings: Dict[str, float]) -> None:
    _save("loadings.json", loadings)


def price_case(
    needs: List[SectionNeed],
    findings: List[RiskFinding],
    sums: List[SumInsured],
    overrides: Optional[Dict[SectionId, float]] = None,
) -> CasePricing:
    """Price every required section from the approved findings and the
    broker-confirmed sums insured. overrides maps section -> loading % where
    the underwriter departed from the band table."""
    overrides = overrides or {}
    rates = load_rates()
    loadings = load_loadings()

    by_section: Dict[SectionId, List[RiskFinding]] = {}
    for f in findings:
        by_section.setdefault(f.section, []).append(f)
    sum_by_section = {s.section: s for s in sums}

    pricing = CasePricing()
    required = sorted(
        (n for n in needs if n.requirement == Requirement.required),
        key=lambda n: section(n.section).number,
    )
    for need in required:
        band = band_for_section(by_section.get(need.section, []))
        rate = float(rates[need.section.value]["rate"])
        table_loading = float(loadings[band])
        applied_loading = float(overrides.get(need.section, table_loading))
        confirmed = sum_by_section.get(need.section)
        line = PricedSection(
            section=need.section,
            band=band,
            rate=rate,
            table_loading=table_loading,
            applied_loading=applied_loading,
            sum_insured=confirmed.amount if confirmed else None,
            basis=confirmed.basis if confirmed else "",
        )
        if line.sum_insured is not None:
            line.base_premium = round(line.sum_insured * rate / 100)
            line.adjusted_premium = round(line.sum_insured * rate / 100 * (1 + applied_loading / 100))
            pricing.base_total += line.base_premium
            pricing.adjusted_total += line.adjusted_premium
        pricing.lines.append(line)
    return pricing
