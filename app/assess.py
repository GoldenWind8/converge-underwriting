"""
The assessment step (docs/SOLUTION_DESIGN.md §4.1). Three calls:

  1. a cheap "fast" call extracts a slim ClientProfile (needed to drive retrieval),
  2. memory.retrieve() finds the k most comparable approved cases,
  3. one "main" call proposes findings, with the playbook in the system prompt
     and the precedents + raw document in the user message.

The LLM decides its own risk factors; guardrails.py verifies them afterwards.
"""

from __future__ import annotations

import re
from typing import Tuple

from . import llm, memory
from .models import CaseRecord, ClientProfile, RiskAssessmentDraft

PROFILE_SYSTEM = (
    "Extract a slim client profile from this commercial-insurance application. "
    "Only what is stated; do not guess. covers_requested uses names like "
    "'Fire', 'Business Interruption', 'Public Liability'. The summary is 1-2 "
    "sentences capturing the client's risk character (trade, size, premises, notable hazards)."
)

ASSESS_SYSTEM = """You are a commercial-insurance underwriting assistant (South African market, amounts in ZAR).
Read the raw application and identify the risk factors YOU judge relevant — you are not
limited to a fixed checklist. For each finding:

- factor_name: short snake_case, e.g. 'uncertified_gas_installation'
- evidence_quote: VERBATIM text copied from the application. Findings whose quote does not
  appear in the document are discarded by a deterministic guardrail — never paraphrase.
- suggested_points by severity: info <= 2, low <= 6, medium <= 12, high <= 20.
- precedent_case_ids / playbook_rule_ids: cite the precedent cases and playbook rules that
  informed the finding. Leave both empty only if it is genuinely novel.
- confidence: 0-1; below 0.6 triggers a human referral.

Weigh the playbook rules and precedent cases heavily — they encode this client's human
underwriters' past decisions. Do not invent facts, and do not compute a total score; a
deterministic layer does the arithmetic.

THE PLAYBOOK (lessons from past human-reviewed cases):
{playbook}
"""


def assess(raw_text: str, use_memory: bool = True) -> Tuple[RiskAssessmentDraft, str]:
    """Returns (draft, engine) — engine is the provider name, disclosed on the
    report. use_memory=False is for the eval harness (blind baseline)."""
    profile = llm.generate(PROFILE_SYSTEM, raw_text, ClientProfile, tier="fast")
    precedents = memory.retrieve(profile, k=5) if use_memory else []
    playbook = memory.load_playbook() if use_memory else memory.PLAYBOOK_STUB

    precedent_text = "\n\n".join(_render_precedent(c) for c in precedents) or "(no comparable past cases on file)"
    user = (
        f"PRECEDENT CASES (approved by human underwriters):\n{precedent_text}\n\n"
        f"NEW APPLICATION DOCUMENT:\n{raw_text}"
    )
    draft = llm.generate(ASSESS_SYSTEM.format(playbook=playbook), user, RiskAssessmentDraft, tier="main")
    # Keep the profile from the dedicated extraction call (it drove retrieval).
    draft.client_profile = profile
    # Keep an unforgeable runtime allow-list for the deterministic citation guardrail.
    draft._retrieved_case_ids = {c.case_id for c in precedents}
    draft._available_rule_ids = set(re.findall(r"\bPB-\d+\b", playbook, flags=re.IGNORECASE))
    return draft, llm.provider()


def _render_precedent(case: CaseRecord) -> str:
    findings = "\n".join(
        f"  - {f.factor_name} [{f.section}] {f.severity.value} ({f.suggested_points} pts)"
        for f in case.approved_findings
    ) or "  (no findings)"
    return (
        f"Case {case.case_id} — {case.summary}\n"
        f"  Outcome: {case.final_band} risk, {case.final_score} pts\n{findings}"
    )
