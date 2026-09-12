"""
Memory: what makes the system "self-learning" (docs/SOLUTION_DESIGN.md §2, §4.2).

Two parts, both file-based and inspectable:

- Case memory   SQLite (data/cases.db), one row per human-approved case.
                Chat-ingested cases are stored provisional and stay invisible
                to retrieval until a human confirms them. Deleted cases stay
                in the table (soft delete, with who/when/why) but leave
                retrieval and the listing.
- Retrieval     given a new client profile and the sections about to be
                assessed, a cheap "fast" model reads one-line summaries of the
                past cases that have findings in those sections and picks the
                k most comparable. Swapping in embeddings later means
                replacing retrieve() only.

There is no rule layer: reviewer corrections and their why-notes travel with
the case and reach the next assessment inside the precedent text
(assess.py::_render_precedent). Governance rule: only approved cases are ever
stored, so the system can't learn from its own unreviewed output.

Set UW_DATA_DIR to relocate all of this (tests point it at a temp dir).
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from . import llm
from .models import CaseRecord, ClientProfile
from .sections import SectionId, section


# --------------------------------------------------------------------------- #
# Paths & storage
# --------------------------------------------------------------------------- #
def data_dir() -> Path:
    d = Path(os.getenv("UW_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(data_dir() / "cases.db")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cases (case_id TEXT PRIMARY KEY, created_at TEXT, record TEXT)"
    )
    return conn


def store(case: CaseRecord) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cases (case_id, created_at, record) VALUES (?, ?, ?)",
            (case.case_id, case.created_at, case.model_dump_json()),
        )


def get_case(case_id: str) -> Optional[CaseRecord]:
    """Any stored case, deleted ones included — the report stays readable."""
    with _connect() as conn:
        row = conn.execute("SELECT record FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return CaseRecord.model_validate_json(row[0]) if row else None


def _rows() -> List[CaseRecord]:
    with _connect() as conn:
        rows = conn.execute("SELECT record FROM cases ORDER BY created_at DESC").fetchall()
    return [CaseRecord.model_validate_json(r[0]) for r in rows]


def all_cases() -> List[CaseRecord]:
    """Every case that has not been deleted."""
    return [c for c in _rows() if c.deleted_at is None]


def deleted_cases() -> List[CaseRecord]:
    return [c for c in _rows() if c.deleted_at is not None]


def active_cases() -> List[CaseRecord]:
    """Cases usable as precedents: everything a human has signed off.
    Provisional (unconfirmed chat-ingested) cases are excluded."""
    return [c for c in all_cases() if not c.provisional]


def confirm_case(case_id: str) -> Optional[CaseRecord]:
    """Human confirmation of a provisional (ingested) case — docs/SOLUTION_DESIGN.md §4.4."""
    case = get_case(case_id)
    if case is None or not case.provisional:
        return case
    case = case.model_copy(update={"provisional": False})
    store(case)
    return case


def delete_case(case_id: str, deleted_by: str, reason: str) -> Optional[CaseRecord]:
    """Soft delete: the row stays (history), the case leaves retrieval and
    the listing. There is deliberately no restore."""
    case = get_case(case_id)
    if case is None:
        return None
    case = case.model_copy(update={
        "deleted_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "deleted_by": deleted_by,
        "deleted_reason": reason,
    })
    store(case)
    return case


def next_case_id() -> str:
    # Counts deleted rows too, so an ID is never reused.
    with _connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    return f"C-{n + 1:04d}"


def reset_demo_data() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM cases")


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
class _RetrievalPick(BaseModel):
    case_ids: List[str] = Field(default_factory=list, description="IDs of the most comparable cases, best first.")


def retrieve(profile: ClientProfile, sections: List[SectionId], k: int = 5) -> List[CaseRecord]:
    """Pick the k most comparable past cases among those with approved
    findings in at least one of the sections about to be assessed. Returns []
    on any retrieval failure — an assessment without precedents beats no
    assessment."""
    wanted = set(sections)
    cases = [c for c in active_cases() if any(f.section in wanted for f in c.approved_findings)]
    if not cases:
        return []
    lines = "\n".join(
        f"{c.case_id}: {c.summary or c.client_profile.summary} "
        f"(industry: {c.client_profile.industry or 'unknown'}; covers: {', '.join(c.client_profile.covers_requested) or 'unknown'})"
        for c in cases
    )
    assessing = ", ".join(section(s).name for s in sorted(wanted, key=lambda s: section(s).number))
    query = (
        f"New client: {profile.summary or profile.business_name or 'unknown'} "
        f"(industry: {profile.industry or 'unknown'}; covers: {', '.join(profile.covers_requested) or 'unknown'})\n"
        f"Sections being assessed: {assessing}\n\n"
        f"Past cases:\n{lines}\n\n"
        f"Pick the up-to-{k} past cases most comparable to the new client for underwriting purposes."
    )
    try:
        pick = llm.generate(
            "You select comparable precedent cases for an insurance underwriter. "
            "Comparable means similar industry, hazards, or risk character — not just similar wording.",
            query,
            _RetrievalPick,
            tier="fast",
        )
    except Exception:  # noqa: BLE001 — retrieval must never sink an assessment
        return []
    by_id = {c.case_id: c for c in cases}
    return [by_id[cid] for cid in pick.case_ids if cid in by_id][:k]
