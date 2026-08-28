"""
The assessment step (docs/SOLUTION_DESIGN.md §4.1, §6.11).

  1. a cheap "fast" call extracts a slim ClientProfile (needed to drive retrieval),
  2. memory.retrieve() finds the k most comparable approved cases,
  3. one "main" call PER CONFIRMED SECTION proposes findings for that section,
     with the section-filtered playbook in the system prompt and the
     section-filtered precedents + raw document in the user message.

The section calls are independent, so they run concurrently; findings are
reassembled in the needs-analysis order. One failed section fails the whole
assessment — no partial drafts.

The LLM decides its own risk factors; guardrails.py verifies them afterwards.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

from . import llm, memory
from .models import (CaseRecord, ClientProfile, Requirement,
                     RiskAssessmentDraft, SectionAssessment, SectionNeed)
from .needs import NO_PRICING
from .sections import MOTOR_SUB_TYPE_NOTES, SectionId, section

PROFILE_SYSTEM = (
    "Extract a slim client profile from this commercial-insurance application. "
    "Only what is stated; do not guess. covers_requested uses names like "
    "'Fire', 'Business Interruption', 'Public Liability'. The summary is 1-2 "
    "sentences capturing the client's risk character (trade, size, premises, notable hazards)."
)

SECTION_SYSTEM = """You are the risk-assessment engine inside Converge Underwriting, a tool used by South African short-term insurance underwriters. An underwriter has a commercial submission in front of them and wants your read on one cover section of it before they form their own view.

Cover section under assessment: {number}. {name}
What this section covers: {scope}
{context_lines}
Assess this section and only this section. The other sections are being assessed separately, so do not range across the whole submission: a fact matters here only insofar as it bears on {name}. Where the same underlying weakness also affects other sections, leave those sections to their own assessment.

Propose the risk findings that matter for this section - typically three to six. For each finding:
- factor_name: short snake_case, e.g. 'uncertified_gas_installation'.
- severity: the standardised scale low / medium / high / severe, used identically across every section and case. Severe is reserved for exposures an underwriter would decline or re-terms without remediation.
- assessment_note: one line naming the reference class the judgement was made against, e.g. 'below standard for a food-production occupancy'. Narrative only — never a number.
- evidence_quote: VERBATIM text copied from the submission. Findings whose quote does not appear in the document, or whose quote is a short generic fragment like 'Yes', are discarded by a deterministic guardrail — never paraphrase, and quote the whole relevant line.
- reasoning: one or two sentences. Why this level for this client.
- precedent_case_ids / playbook_rule_ids: cite the precedent cases and playbook rules that informed the finding. Leave both empty only if it is genuinely novel.
- confidence: 0-1; below 0.6 triggers a human referral.

Cover distinct dimensions of this section's risk rather than restating one dimension several ways. Prefer what this specific submission makes salient over a generic checklist.

{no_pricing}

Weigh the playbook rules and precedent cases heavily — they encode this client's human underwriters' past decisions.

THE PLAYBOOK (rules applicable to this section):
{playbook}"""


def assess_profile(raw_text: str) -> ClientProfile:
    return llm.generate(PROFILE_SYSTEM, raw_text, ClientProfile, tier="fast")


def assess_sections(
    raw_text: str,
    profile: ClientProfile,
    needs: List[SectionNeed],
    use_memory: bool = True,
) -> Tuple[RiskAssessmentDraft, str]:
    """Assess every section the confirmed needs table marks required — one
    main-model call each, run concurrently, findings reassembled in the
    needs-analysis order. Returns (draft, engine); engine is the provider name,
    disclosed on the report. use_memory=False is for the eval harness (blind
    baseline)."""
    precedents = memory.retrieve(profile, k=5) if use_memory else []
    playbook = memory.load_playbook() if use_memory else memory.PLAYBOOK_STUB

    required = sorted(
        (n for n in needs if n.requirement == Requirement.required),
        key=lambda n: section(n.section).number,
    )

    draft = RiskAssessmentDraft(client_profile=profile)
    if required:
        with ThreadPoolExecutor(max_workers=len(required)) as pool:
            assessments = list(pool.map(
                lambda need: _assess_one_section(raw_text, need, playbook, precedents),
                required,
            ))
        for need, sa in zip(required, assessments):
            for f in sa.findings:
                draft.findings.append(f.model_copy(update={"section": need.section}))
            if sa.memory_note:
                draft.overall_notes.append(f"{section(need.section).name}: {sa.memory_note}")

    # Keep an unforgeable runtime allow-list for the deterministic citation guardrail.
    draft._retrieved_case_ids = {c.case_id for c in precedents}
    draft._available_rule_ids = set(re.findall(r"\bPB-\d+\b", playbook, flags=re.IGNORECASE))
    return draft, llm.provider()


def _assess_one_section(
    raw_text: str,
    need: SectionNeed,
    playbook: str,
    precedents: List[CaseRecord],
) -> SectionAssessment:
    cover = section(need.section)

    context_lines = ""
    if need.reason:
        context_lines += f"Why this section is in scope for this client: {need.reason}\n"
    if need.section == SectionId.motor and need.motor_sub_type:
        context_lines += (
            f"Motor sub-type selected: {MOTOR_SUB_TYPE_NOTES[need.motor_sub_type]} "
            "Assess only what this sub-type actually exposes the insurer to — "
            "own-damage exposure is not worth assessing under third-party-only cover.\n"
        )

    system = SECTION_SYSTEM.format(
        number=cover.number,
        name=cover.name,
        scope=cover.scope,
        context_lines=context_lines,
        no_pricing=NO_PRICING,
        playbook=memory.rules_for_section(playbook, need.section),
    )
    precedent_text = "\n\n".join(
        text for c in precedents if (text := _render_precedent(c, need.section))
    ) or "(no comparable precedent findings for this section)"
    user = (
        f"PRECEDENT FINDINGS for the {cover.name} section (approved by human underwriters):\n"
        f"{precedent_text}\n\n"
        f"Here is the commercial submission. Assess it for the {cover.name} section.\n\n"
        f"<submission>\n{raw_text.strip()}\n</submission>"
    )
    return llm.generate(system, user, SectionAssessment, tier="main")


def _render_precedent(case: CaseRecord, section_id: SectionId) -> str:
    """A precedent case's findings for one section; empty if it has none."""
    relevant = [f for f in case.approved_findings if f.section == section_id]
    if not relevant:
        return ""
    findings = "\n".join(
        f"  - {f.factor_name} [{f.severity.value}] {f.reasoning}"
        for f in relevant
    )
    return (
        f"Case {case.case_id} — {case.summary}\n"
        f"  Outcome: {case.final_band} band\n{findings}"
    )
