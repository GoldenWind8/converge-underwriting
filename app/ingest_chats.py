"""
Bootstrap memory from historical chat transcripts (docs/SOLUTION_DESIGN.md §4.4).

    python -m app.ingest_chats [chats_dir]      # default: sample_data/chats

Per transcript: an LLM extracts the client profile and the risks the human
underwriter actually decided on -> stored as a PROVISIONAL CaseRecord
(source="chat_ingestion"). Transcripts with no risk decision are skipped.

Governance (docs/SOLUTION_DESIGN.md §4.4): LLM-extracted cases never enter
the live memory ungated. They are stored provisional — invisible to retrieval —
until a human confirms each one on the /cases page, and ingestion never writes
to the playbook.
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from . import llm, memory
from .guardrails import band_for_findings
from .models import CaseRecord, ClientProfile, RiskFinding
from .sections import COVER_SECTIONS


class IngestedCase(BaseModel):
    """What one transcript yields."""
    client_profile: ClientProfile
    summary: str = Field("", description="1-2 sentence description of the client and its risk character.")
    approved_findings: List[RiskFinding] = Field(default_factory=list)
    contains_risk_decision: bool = Field(True, description="False if the chat contains no underwriting decision.")


INGEST_SYSTEM = (
    "You read a historical chat between an insurance broker/client and a human underwriter. "
    "Extract the client profile and every risk factor the HUMAN decided on (these count as "
    "human-approved findings): factor_name in snake_case, the severity they settled on "
    "(low/medium/high/severe), the cover section it belongs to, and the evidence phrase from "
    "the chat. Section must be one of: "
    + ", ".join(s.id.value for s in COVER_SECTIONS)
    + ". Set contains_risk_decision=false if no risk decision was made. "
    "Do not invent findings the human did not make."
)


def ingest_file(path: Path) -> Optional[CaseRecord]:
    extracted = llm.generate(INGEST_SYSTEM, path.read_text(encoding="utf-8"), IngestedCase, tier="fast")
    if not extracted.contains_risk_decision or not extracted.approved_findings:
        return None

    case = CaseRecord(
        case_id=memory.next_case_id(),
        created_at=_dt.datetime.now().isoformat(timespec="seconds"),
        source="chat_ingestion",
        client_profile=extracted.client_profile,
        summary=extracted.summary or extracted.client_profile.summary,
        draft_findings=extracted.approved_findings,
        approved_findings=extracted.approved_findings,
        corrections=[],
        final_band=band_for_findings(extracted.approved_findings),
        provisional=True,
    )
    memory.store(case)
    return case


def main(chats_dir: str = "sample_data/chats") -> None:
    llm.require()
    paths = sorted(Path(chats_dir).glob("*.md"))
    if not paths:
        print(f"No .md transcripts found in {chats_dir}")
        return
    ingested = 0
    for path in paths:
        case = ingest_file(path)
        if case is None:
            print(f"  skipped {path.name} (no risk decision found)")
            continue
        ingested += 1
        print(f"  {case.case_id} <- {path.name}: {len(case.approved_findings)} finding(s), "
              f"{case.final_band} band. Stored PROVISIONAL — confirm it on /cases before "
              f"it becomes a precedent.")
    print(f"\nIngested {ingested}/{len(paths)} transcript(s) as provisional cases. "
          f"Memory holds {len(memory.all_cases())} case(s) total; only confirmed ones "
          f"are retrieved as precedents. See /cases.")


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
