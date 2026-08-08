"""
Tiny eval harness (docs/SOLUTION_DESIGN.md §6.9): prove the system is learning.

    python -m app.evaluate

For each stored case, rebuild a pseudo-application from its evidence and run
the per-section assessor twice — memory OFF (no precedents, stub playbook) vs
memory ON — then measure how many of the human-approved findings each run
recovered (matched on factor_name; severity agreement reported separately).

The sections assessed are the case's confirmed needs table where it has one,
else the sections its approved findings actually touch — so the measurement
covers the same ground the human decision did.

The pitch number: "precedent-informed assessments matched historical
underwriter decisions X% vs Y% blind".
"""

from __future__ import annotations

from contextlib import contextmanager

from . import memory
from .assess import assess_sections
from .models import CaseRecord, Requirement, SectionNeed


def pseudo_application(case: CaseRecord) -> str:
    """Reconstruct an application-like document from a stored case."""
    p = case.client_profile
    lines = [
        f"Business name: {p.business_name or 'Unknown'}",
        f"Industry: {p.industry or 'Unknown'}",
        f"Number of employees: {p.employees or ''}",
    ]
    for cover in p.covers_requested:
        lines.append(f"{cover} cover: Yes")
    lines += [f.evidence_quote for f in case.approved_findings if f.evidence_quote]
    return "\n".join(lines)


def needs_for(case: CaseRecord) -> list[SectionNeed]:
    """The case's confirmed needs table, or one reconstructed from the
    sections its approved findings touch (older / ingested cases)."""
    required = [n for n in case.needs if n.requirement == Requirement.required]
    if required:
        return required
    seen = []
    for f in case.approved_findings:
        if f.section not in seen:
            seen.append(f.section)
    return [SectionNeed(section=s, requirement=Requirement.required,
                        reason="reconstructed from the approved findings") for s in seen]


@contextmanager
def _held_out(case: CaseRecord):
    """Leave-one-out: remove the case from memory while it is being assessed,
    so retrieval can't just find the answer key. (Playbook rules it contributed
    remain — reported as a caveat below.)"""
    with memory._connect() as conn:
        conn.execute("DELETE FROM cases WHERE case_id = ?", (case.case_id,))
    try:
        yield
    finally:
        memory.store(case)


def score_case(case: CaseRecord, use_memory: bool) -> tuple:
    """Returns (recovered, severity_matched, total_approved)."""
    with _held_out(case):
        draft, _ = assess_sections(
            pseudo_application(case), case.client_profile, needs_for(case),
            use_memory=use_memory,
        )
    proposed = {f.factor_name: f for f in draft.findings}
    approved = case.approved_findings
    recovered = [f for f in approved if f.factor_name in proposed]
    sev_match = [f for f in recovered if proposed[f.factor_name].severity == f.severity]
    return len(recovered), len(sev_match), len(approved)


def main() -> None:
    from . import llm

    llm.require()
    cases = memory.all_cases()
    if not cases:
        print("No cases in memory — run the app or `python -m app.ingest_chats` first.")
        return

    totals = {"off": [0, 0, 0], "on": [0, 0, 0]}
    print(f"Evaluating {len(cases)} case(s)...\n")
    for case in cases:
        for mode, use in (("off", False), ("on", True)):
            r, s, t = score_case(case, use_memory=use)
            totals[mode][0] += r
            totals[mode][1] += s
            totals[mode][2] += t
        print(f"  {case.case_id} ({case.client_profile.industry or 'unknown'}): "
              f"{len(case.approved_findings)} approved finding(s) over "
              f"{len(needs_for(case))} section(s)")

    print("\n                    factors recovered   severity also matched")
    for mode in ("off", "on"):
        r, s, t = totals[mode]
        label = "memory OFF" if mode == "off" else "memory ON "
        pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"
        print(f"  {label}          {r}/{t} ({pct(r, t)})          {s}/{t} ({pct(s, t)})")
    summary = llm.usage_summary()
    print("\n(Matched on factor_name against the human-approved findings, leave-one-out:")
    print(" the case under test is removed from case memory while it is assessed.")
    print(" Caveat: playbook rules it contributed remain in force.)")
    print(f"\nModel usage this run: {summary['calls']} call(s), "
          f"{summary['input_tokens'] + summary['output_tokens']} tokens"
          + (f", ${summary['cost_usd']:.2f}" if summary["cost_usd"] else "") + ".")


if __name__ == "__main__":
    main()
