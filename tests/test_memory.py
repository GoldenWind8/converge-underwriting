"""Case memory, retrieval, playbook section filtering, and reflection
(with the LLM faked)."""

from app import llm, memory
from app.memory import _PlaybookUpdate, _RetrievalPick
from app.models import (CaseRecord, ClientProfile, Correction, RiskFinding,
                        Severity)
from app.sections import SectionId


def _case(case_id="C-0001", industry="restaurant", factor="uncertified_gas_installation",
          provisional=False) -> CaseRecord:
    finding = RiskFinding(
        factor_name=factor, section=SectionId.fire, severity=Severity.high,
        evidence_quote="no gas certificate on file", reasoning="Uncertified gas installation.",
        confidence=1.0,
    )
    return CaseRecord(
        case_id=case_id, created_at="2026-07-09T10:00:00", source="assessment",
        client_profile=ClientProfile(business_name="X", industry=industry,
                                     covers_requested=["Fire"], summary=f"{industry}; covers: Fire"),
        summary=f"{industry}; covers: Fire",
        draft_findings=[finding], approved_findings=[finding],
        corrections=[Correction(type="severity_changed", factor_name=factor,
                                detail="medium -> high", note="Gas plus no certificate is never medium.")],
        final_band="Elevated", provisional=provisional,
    )


def test_store_and_load_roundtrip():
    memory.store(_case())
    loaded = memory.get_case("C-0001")
    assert loaded is not None
    assert loaded.approved_findings[0].factor_name == "uncertified_gas_installation"
    assert loaded.corrections[0].note == "Gas plus no certificate is never medium."
    assert memory.next_case_id() == "C-0002"


def test_retrieve_with_empty_memory_makes_no_llm_call(fake_llm):
    assert memory.retrieve(ClientProfile(industry="florist"), k=3) == []
    assert fake_llm.calls == []


def test_retrieval_returns_the_llm_picks_in_order(fake_llm):
    memory.store(_case("C-0001", industry="restaurant"))
    memory.store(_case("C-0002", industry="panel beater"))
    fake_llm.register(_RetrievalPick, _RetrievalPick(case_ids=["C-0002", "C-0001"]))
    hits = memory.retrieve(ClientProfile(industry="panel beater"), k=1)
    assert [c.case_id for c in hits] == ["C-0002"]


def test_provisional_cases_are_invisible_to_retrieval(fake_llm):
    memory.store(_case("C-0001", provisional=True))
    # No active cases -> no model call, no precedents.
    assert memory.retrieve(ClientProfile(industry="restaurant"), k=3) == []
    assert fake_llm.calls == []

    memory.confirm_case("C-0001")
    fake_llm.register(_RetrievalPick, _RetrievalPick(case_ids=["C-0001"]))
    hits = memory.retrieve(ClientProfile(industry="restaurant"), k=3)
    assert [c.case_id for c in hits] == ["C-0001"]


def test_retrieval_failure_returns_no_precedents(monkeypatch):
    memory.store(_case())

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm, "generate", boom)
    assert memory.retrieve(ClientProfile(industry="restaurant"), k=3) == []


PLAYBOOK = """# Underwriting Playbook

Some preamble.

## PB-001 · [fire] gas installations
Absence of a certificate is HIGH.
Supporting cases: C-0001

## PB-002 · [theft] cash on site overnight
Refer when takings sleep on the premises.
Supporting cases: C-0002

## PB-003 · [general] silent submissions
A submission silent on security is a consider, not a pass.
Supporting cases: C-0003

## PB-004 · untagged legacy rule
Kept for every section until it is retagged.
Supporting cases: C-0004
"""


def test_rules_are_filtered_to_their_section():
    fire = memory.rules_for_section(PLAYBOOK, SectionId.fire)
    assert "PB-001" in fire
    assert "PB-002" not in fire  # the Theft lesson is structurally unable to reach Fire
    assert "PB-003" in fire      # general applies everywhere
    assert "PB-004" in fire      # untagged rules are kept on purpose
    assert "Some preamble." in fire

    theft = memory.rules_for_section(PLAYBOOK, SectionId.theft)
    assert "PB-002" in theft
    assert "PB-001" not in theft


def test_rules_filter_handles_a_playbook_with_no_rules():
    assert "no lessons" in memory.rules_for_section(memory.PLAYBOOK_STUB, SectionId.fire).lower()


def test_reflection_proposal_waits_for_human_approval(fake_llm):
    original = memory.load_playbook()
    updated = original + "\n## PB-001 · [fire] proposed lesson\nTreat as HIGH.\nSupporting cases: C-0001\n"
    fake_llm.register(_PlaybookUpdate, _PlaybookUpdate(
        playbook_markdown=updated, change_note="Proposed PB-001."))

    proposal = memory.propose_reflection(_case())

    assert proposal is not None
    assert "PB-001" in proposal.proposed_playbook
    assert memory.load_playbook() == original, "proposal must not silently change policy"


def test_reflection_prompt_carries_the_reviewers_why_note(fake_llm):
    fake_llm.register(_PlaybookUpdate, _PlaybookUpdate(
        playbook_markdown=memory.load_playbook(), change_note="nothing"))
    memory.propose_reflection(_case())
    _, _, _, user = fake_llm.calls[-1]
    assert "Gas plus no certificate is never medium." in user


def test_reflection_is_noop_when_playbook_unchanged(fake_llm):
    fake_llm.register(_PlaybookUpdate, _PlaybookUpdate(
        playbook_markdown=memory.load_playbook(), change_note="nothing to learn"))
    assert memory.propose_reflection(_case()) is None


def test_save_playbook_keeps_history():
    memory.load_playbook()
    memory.save_playbook("# Underwriting Playbook\n\n## PB-001 · [fire] x\nLesson.\n")
    assert list((memory.data_dir() / "playbook_history").glob("*.md")), "old version must be archived"
