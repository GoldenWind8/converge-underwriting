"""
Memory: what makes the system "self-learning" (docs/SOLUTION_DESIGN.md §2, §4.2).

Three parts, all file-based and inspectable:

- Case memory   SQLite (data/cases.db), one row per human-approved case.
                Chat-ingested cases are stored provisional and stay invisible
                to retrieval until a human confirms them.
- Retrieval     given a new client profile, a cheap "fast" model reads one-line
                summaries of past cases and picks the k most comparable.
                Swapping in embeddings later means replacing retrieve() only.
- Playbook      data/playbook.md — compact natural-language lessons distilled
                from reviewer corrections. Rules carry a section tag, and each
                per-section assessment prompt receives only the rules for its
                section (plus untagged/general ones). Every save keeps a copy
                in data/playbook_history/.

Reflection (propose_reflection()) runs after each human sign-off: it diffs
draft vs approved and PROPOSES a playbook update — nothing is applied until
the underwriter accepts it (human gate 3). Governance rule: only approved
cases are ever stored, so the system can't learn from its own unreviewed output.

Set UW_DATA_DIR to relocate all of this (tests point it at a temp dir).
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from . import llm
from .models import CaseRecord, ClientProfile
from .sections import SectionId

PLAYBOOK_STUB = "# Underwriting Playbook\n\nNo lessons learned yet — rules appear here as reviewers correct assessments.\n"


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
    with _connect() as conn:
        row = conn.execute("SELECT record FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return CaseRecord.model_validate_json(row[0]) if row else None


def all_cases() -> List[CaseRecord]:
    with _connect() as conn:
        rows = conn.execute("SELECT record FROM cases ORDER BY created_at DESC").fetchall()
    return [CaseRecord.model_validate_json(r[0]) for r in rows]


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


def next_case_id() -> str:
    with _connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    return f"C-{n + 1:04d}"


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
class _RetrievalPick(BaseModel):
    case_ids: List[str] = Field(default_factory=list, description="IDs of the most comparable cases, best first.")


def retrieve(profile: ClientProfile, k: int = 5) -> List[CaseRecord]:
    """Pick the k most comparable past cases. Returns [] on any retrieval
    failure — an assessment without precedents beats no assessment."""
    cases = active_cases()
    if not cases:
        return []
    lines = "\n".join(
        f"{c.case_id}: {c.summary or c.client_profile.summary} "
        f"(industry: {c.client_profile.industry or 'unknown'}; covers: {', '.join(c.client_profile.covers_requested) or 'unknown'})"
        for c in cases
    )
    query = (
        f"New client: {profile.summary or profile.business_name or 'unknown'} "
        f"(industry: {profile.industry or 'unknown'}; covers: {', '.join(profile.covers_requested) or 'unknown'})\n\n"
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


# --------------------------------------------------------------------------- #
# Playbook
# --------------------------------------------------------------------------- #
def playbook_path() -> Path:
    return data_dir() / "playbook.md"


def load_playbook() -> str:
    p = playbook_path()
    if not p.exists():
        p.write_text(PLAYBOOK_STUB, encoding="utf-8")
    return p.read_text(encoding="utf-8")


def save_playbook(text: str) -> None:
    p = playbook_path()
    history = data_dir() / "playbook_history"
    history.mkdir(exist_ok=True)
    if p.exists():
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        (history / f"playbook-{stamp}.md").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    temporary = p.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(p)


_RULE_HEADER = re.compile(r"^##\s+PB-\d+.*$", re.MULTILINE | re.IGNORECASE)
_SECTION_TAG = re.compile(r"\[([a-z0-9-]+)\]")


def rules_for_section(playbook: str, section_id: SectionId) -> str:
    """The playbook filtered to one section: its preamble, plus every rule
    tagged [<section-id>] or [general] or carrying no tag at all. Untagged
    rules are kept on purpose — better an extra lesson than a silently
    withheld one."""
    headers = list(_RULE_HEADER.finditer(playbook))
    if not headers:
        return playbook
    kept = [playbook[: headers[0].start()].rstrip()]
    for index, match in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(playbook)
        tag = _SECTION_TAG.search(match.group(0))
        if tag is None or tag.group(1) in (section_id.value, "general"):
            kept.append(playbook[match.start():end].rstrip())
    if len(kept) == 1:
        kept.append("(no playbook rules yet for this section)")
    return "\n\n".join(part for part in kept if part) + "\n"


def reset_demo_data() -> None:
    """Reset active POC memory while retaining the archived playbook history."""
    with _connect() as conn:
        conn.execute("DELETE FROM cases")
    save_playbook(PLAYBOOK_STUB)


# --------------------------------------------------------------------------- #
# Reflection — the learning step, run after every human sign-off
# --------------------------------------------------------------------------- #
class _PlaybookUpdate(BaseModel):
    playbook_markdown: str = Field(..., description="The complete updated playbook markdown.")
    change_note: str = Field(..., description="One sentence describing what changed and why.")


class LearningProposal(BaseModel):
    case_id: str
    current_playbook: str
    proposed_playbook: str
    change_note: str


REFLECT_SYSTEM = """You maintain an insurance underwriting playbook: compact, natural-language
lessons distilled from human reviewers' decisions. You receive the current playbook and one
newly approved case (with the reviewer's corrections, if any). Return the complete updated playbook.

Rules for the playbook:
- Each rule is a markdown section: '## PB-NNN · [section-id] short title' followed by 2-3
  sentences stating the lesson, then a 'Supporting cases: <ids>' line. The section-id tag is
  the cover section the lesson belongs to (e.g. [fire], [motor], [theft]); use [general] only
  for a lesson that genuinely spans sections. Per-section assessments only receive the rules
  tagged for their section, so an untagged or mis-tagged rule reaches the wrong prompt.
- Rule IDs are stable — never renumber existing rules.
- Add a rule when a correction teaches something generalisable; strengthen an existing rule
  (add the supporting case id, firm up the wording) when the case confirms it; weaken or
  retire a rule contradicted by the reviewer's decision.
- The reviewer's own 'why' notes are the most direct statement of the lesson — quote or
  paraphrase them in the rule where they exist.
- Approvals with no corrections may still strengthen matching rules.
- Keep the whole playbook under ~2500 tokens: consolidate similar rules before adding new ones.
- Never invent lessons the case does not support."""


def propose_reflection(case: CaseRecord) -> Optional[LearningProposal]:
    """Draft, but do not apply, a playbook update from an approved case."""
    playbook = load_playbook()
    corrections = "\n".join(
        f"- {c.type}: {c.factor_name} {c.detail}".strip()
        + (f' — reviewer\'s note: "{c.note}"' if c.note else "")
        for c in case.corrections
    ) or "(none — approved as drafted)"
    approved = "\n".join(
        f"- {f.factor_name} [{f.section.value}] severity={f.severity.value}"
        + f": {f.reasoning}"
        for f in case.approved_findings
    ) or "(no findings)"
    user = (
        f"CURRENT PLAYBOOK:\n{playbook}\n\n"
        f"NEW APPROVED CASE {case.case_id} ({case.client_profile.industry or 'unknown industry'}):\n"
        f"Summary: {case.summary}\n"
        f"Approved findings:\n{approved}\n"
        f"Reviewer corrections (draft -> approved):\n{corrections}\n"
    )
    update = llm.generate(REFLECT_SYSTEM, user, _PlaybookUpdate, tier="main")
    if update.playbook_markdown.strip() and update.playbook_markdown.strip() != playbook.strip():
        return LearningProposal(
            case_id=case.case_id,
            current_playbook=playbook,
            proposed_playbook=update.playbook_markdown,
            change_note=update.change_note,
        )
    return None
