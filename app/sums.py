"""
Sum-insured extraction: one fast-tier call that lifts the figures the client
STATED in the submission, per cover section, so the broker can confirm or
correct them at gate 1 before anything is priced.

This is the one model call that deliberately sits outside the NO_PRICING
boundary — and it is still not pricing: it transcribes stated amounts, it
never estimates one. Whatever comes back is only a pre-fill; the number the
pricing engine sees is the number the broker confirmed on the needs form.
"""

from __future__ import annotations

from typing import Dict, List

from . import llm
from .models import SumInsured, SumsInsured
from .sections import COVER_SECTIONS, SectionId

_SECTION_LINES = "\n".join(
    f"- {s.id.value} ({s.number}. {s.name}): {s.scope}" for s in COVER_SECTIONS
)

SUMS_SYSTEM = f"""You transcribe sums insured from a South African commercial insurance submission. For each cover section below, report the amount the submission STATES for it, in whole rand.

Rules — transcription, not judgement:
- Only figures the submission actually states. If no figure is stated for a section, amount is null and basis is empty. Never estimate, never infer a "typical" value.
- Where a section's sum insured is naturally the total of several clearly labelled figures (e.g. fire cover over plant, stock and contents), you may add them — and the basis must then quote each component with its amount so the broker can check the arithmetic.
- basis quotes the labelled amounts you used, e.g. "Plant R10 000 000 + stock (average) R5 000 000 + contents R3 000 000".
- For liability sections, the "sum insured" is the stated limit of indemnity, if any.
- Amounts are annual/current values as stated; strip currency symbols and separators (R30 000 000 -> 30000000).
- One entry per section, using the section id verbatim.

The cover sections:

{_SECTION_LINES}"""


def extract_sums(raw_text: str) -> Dict[SectionId, SumInsured]:
    user = (
        "Here is the commercial submission. Transcribe the stated sum insured per cover section.\n\n"
        f"<submission>\n{raw_text.strip()}\n</submission>"
    )
    extracted = llm.generate(SUMS_SYSTEM, user, SumsInsured, tier="fast")
    return _repair(extracted.items)


def _repair(items: List[SumInsured]) -> Dict[SectionId, SumInsured]:
    """Exactly one entry per section: skipped sections become 'not stated',
    duplicates keep the first entry, negative amounts are discarded."""
    by_section: Dict[SectionId, SumInsured] = {}
    for item in items:
        if item.amount is not None and item.amount < 0:
            item = item.model_copy(update={"amount": None, "basis": ""})
        by_section.setdefault(item.section, item)
    return {
        cover.id: by_section.get(cover.id) or SumInsured(section=cover.id)
        for cover in COVER_SECTIONS
    }
