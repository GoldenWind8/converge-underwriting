"""Case memory, retrieval, and reflection (with the LLM faked)."""

import pytest

from app import llm, memory
from app.memory import _PlaybookUpdate, _RetrievalPick
from app.models import CaseRecord, ClientProfile, Correction, RiskFinding, Severity


def _case(case_id="C-0001", industry="restaurant", factor="uncertified_gas_installation") -> CaseRecord:
    finding = RiskFinding(
        factor_name=factor, section="Fire", severity=Severity.high, suggested_points=15,
        evidence_quote="no gas certificate", reasoning="Uncertified gas installation.",
        confidence=1.0,
    )
    return CaseRecord(
        case_id=case_id, created_at="2026-07-09T10:00:00", source="assessment",
        client_profile=ClientProfile(business_name="X", industry=industry,
                                     covers_requested=["Fire"], summary=f"{industry}; covers: Fire"),
        summary=f"{industry}; covers: Fire",
        draft_findings=[finding], approved_findings=[finding],
        corrections=[Correction(type="severity_changed", factor_name=factor, detail="medium -> high")],
        final_score=15, final_band="Moderate",
    )


def test_store_and_load_roundtrip():
    memory.store(_case())
    loaded = memory.get_case("C-0001")
    assert loaded is not None
    assert loaded.approved_findings[0].factor_name == "uncertified_gas_installation"
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


def test_retrieval_failure_returns_no_precedents(monkeypatch):
    memory.store(_case())

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm, "generate", boom)
    assert memory.retrieve(ClientProfile(industry="restaurant"), k=3) == []


def test_reflection_saves_playbook_and_keeps_history(fake_llm):
    updated = memory.PLAYBOOK_STUB + "\n## PB-001 · restaurant — uncertified_gas_installation\nTreat as HIGH.\nSupporting cases: C-0001\n"
    fake_llm.register(_PlaybookUpdate, _PlaybookUpdate(
        playbook_markdown=updated, change_note="Added PB-001 for uncertified gas installations."))
    note = memory.reflect(_case())
    assert note == "Added PB-001 for uncertified gas installations."
    assert "PB-001" in memory.load_playbook()
    assert list((memory.data_dir() / "playbook_history").glob("*.md")), "old version must be archived"


def test_reflection_is_noop_when_playbook_unchanged(fake_llm):
    fake_llm.register(_PlaybookUpdate, _PlaybookUpdate(
        playbook_markdown=memory.load_playbook(), change_note="nothing to learn"))
    assert memory.reflect(_case()) is None


def test_reflection_proposal_waits_for_human_approval(fake_llm):
    original = memory.load_playbook()
    updated = original + "\n## PB-001 · proposed lesson\nTreat as HIGH.\nSupporting cases: C-0001\n"
    fake_llm.register(_PlaybookUpdate, _PlaybookUpdate(
        playbook_markdown=updated, change_note="Proposed PB-001."))

    proposal = memory.propose_reflection(_case())

    assert proposal is not None
    assert "PB-001" in proposal.proposed_playbook
    assert memory.load_playbook() == original, "proposal must not silently change policy"
