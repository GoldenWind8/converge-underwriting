"""
Needs determination (step 2 of the pipeline): which of the 18 cover sections
does this business actually need? Runs before anything is assessed, and its
output goes to the underwriter for confirmation (human gate 1) — what gate 1
says "required" is what gets assessed.
"""

from __future__ import annotations

from typing import List

from . import llm
from .models import NeedsDetermination, Requirement, SectionNeed
from .sections import (COVER_SECTIONS, MOTOR_SUB_TYPE_NOTES, SectionId)

# Hard product boundary, stated in every prompt: this system assesses risk,
# it never prices it, and it carries no numeric score of any kind.
NO_PRICING = (
    "Hard boundary: you are assessing risk, not pricing it. Never produce a premium, "
    "a rand or currency amount, a rate, a sum insured, a loss ratio, a claims frequency "
    "or severity figure, a probability, or any calculation. No formulas, no arithmetic. "
    "If you feel the pull to quantify, express the judgement on the categorical scale instead."
)

_SECTION_LINES = "\n".join(
    f"- {s.id.value} ({s.number}. {s.name}): {s.scope}" for s in COVER_SECTIONS
)
_MOTOR_LINES = "\n".join(f"- {t.value}: {note}" for t, note in MOTOR_SUB_TYPE_NOTES.items())

NEEDS_SYSTEM = f"""You are the needs-analysis engine inside Converge Underwriting, a tool used by South African short-term insurance underwriters and brokers. A commercial submission has come in. Before anyone assesses risk, someone has to work out which cover sections this business actually needs.

Go through every section below and place it in one of three buckets:
- required: the submission shows an exposure this section is for. The business would be exposed without it.
- consider: plausibly relevant, but the submission does not settle it - the exposure may be small, or a fact you would need is missing. Say which fact.
- not-applicable: the submission positively rules it out. Not "probably fine" - genuinely no exposure, or someone else carries it.

Decide from the submission, not from what a business of this type usually buys. Concretely: a business with no vehicles does not need Motor; a tenant whose landlord insures the structure does not need Buildings Combined; a business that handles no cash does not need Money; a business that does not repair or sell vehicles for a living does not need Motor Traders. Where the submission is silent on something material, that is "consider" with the missing fact named - not "required" on a guess, and not "not-applicable" on an assumption.

Be willing to mark sections not-applicable. An analysis that marks everything required is the same as no analysis, and it puts the client on cover they cannot claim under.

Give exactly one entry per section, using the section id verbatim, in the order listed.

{NO_PRICING}

The cover sections:

{_SECTION_LINES}

Motor sub-types. If the motor section is required or worth considering, choose the sub-type that fits what the submission says about the vehicles and how the business depends on them, and justify that choice in the reason. Use the id:
{_MOTOR_LINES}"""


def determine_needs(raw_text: str) -> NeedsDetermination:
    user = (
        "Here is the commercial submission. Work out which cover sections this business needs.\n\n"
        f"<submission>\n{raw_text.strip()}\n</submission>"
    )
    determination = llm.generate(NEEDS_SYSTEM, user, NeedsDetermination, tier="main")
    determination.needs = _repair(determination.needs)
    return determination


def _repair(needs: List[SectionNeed]) -> List[SectionNeed]:
    """Guarantee exactly one entry per section, in canonical order. A section
    the model skipped becomes 'consider' with an honest reason — never silently
    invented, never silently dropped."""
    by_section = {}
    for need in needs:
        by_section.setdefault(need.section, need)  # first entry wins on duplicates
    repaired = []
    for cover in COVER_SECTIONS:
        need = by_section.get(cover.id) or SectionNeed(
            section=cover.id,
            requirement=Requirement.consider,
            reason="The model did not classify this section — review manually.",
        )
        if need.section != SectionId.motor:
            need = need.model_copy(update={"motor_sub_type": None})
        repaired.append(need)
    return repaired
