"""Case memory: storage, section-scoped retrieval, and soft delete
(with the LLM faked)."""

from app import llm, memory
from app.memory import _RetrievalPick
from app.models import (CaseRecord, ClientProfile, Correction, RiskFinding,
                        Severity)
from app.sections import SectionId


def _case(case_id="C-0001", industry="restaurant", factor="uncertified_gas_installation",
          section=SectionId.fire, provisional=False) -> CaseRecord:
    finding = RiskFinding(
        factor_name=factor, section=section, severity=Severity.high,
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


def test_old_records_with_playbook_fields_still_load():
    stale = _case().model_dump()
    stale["approved_findings"][0]["playbook_rule_ids"] = ["PB-001"]
    stale["draft_findings"][0]["playbook_rule_ids"] = ["PB-001"]
    loaded = CaseRecord.model_validate(stale)
    assert loaded.approved_findings[0].factor_name == "uncertified_gas_installation"
    assert not hasattr(loaded.approved_findings[0], "playbook_rule_ids")


def test_retrieve_with_empty_memory_makes_no_llm_call(fake_llm):
    assert memory.retrieve(ClientProfile(industry="florist"), [SectionId.fire], k=3) == []
    assert fake_llm.calls == []


def test_retrieval_returns_the_llm_picks_in_order(fake_llm):
    memory.store(_case("C-0001", industry="restaurant"))
    memory.store(_case("C-0002", industry="panel beater"))
    fake_llm.register(_RetrievalPick, _RetrievalPick(case_ids=["C-0002", "C-0001"]))
    hits = memory.retrieve(ClientProfile(industry="panel beater"), [SectionId.fire], k=1)
    assert [c.case_id for c in hits] == ["C-0002"]


def test_retrieval_is_scoped_to_the_sections_being_assessed(fake_llm):
    memory.store(_case("C-0001", section=SectionId.motor, factor="street_parked_overnight"))
    memory.store(_case("C-0002", section=SectionId.fire))

    # A Motor-only case is never a candidate for a Fire-only assessment.
    fake_llm.register(_RetrievalPick, lambda system, user: _RetrievalPick(
        case_ids=["C-0001", "C-0002"]))
    hits = memory.retrieve(ClientProfile(industry="restaurant"), [SectionId.fire], k=5)
    assert [c.case_id for c in hits] == ["C-0002"]
    _, _, _, user = fake_llm.calls[-1]
    assert "C-0001" not in user, "the picker never even sees the Motor case"
    assert "Sections being assessed: Fire" in user

    # With no case in the wanted sections there is nothing to pick from — no call.
    fake_llm.calls.clear()
    assert memory.retrieve(ClientProfile(industry="restaurant"), [SectionId.theft], k=5) == []
    assert fake_llm.calls == []


def test_provisional_cases_are_invisible_to_retrieval(fake_llm):
    memory.store(_case("C-0001", provisional=True))
    # No active cases -> no model call, no precedents.
    assert memory.retrieve(ClientProfile(industry="restaurant"), [SectionId.fire], k=3) == []
    assert fake_llm.calls == []

    memory.confirm_case("C-0001")
    fake_llm.register(_RetrievalPick, _RetrievalPick(case_ids=["C-0001"]))
    hits = memory.retrieve(ClientProfile(industry="restaurant"), [SectionId.fire], k=3)
    assert [c.case_id for c in hits] == ["C-0001"]


def test_retrieval_failure_returns_no_precedents(monkeypatch):
    memory.store(_case())

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm, "generate", boom)
    assert memory.retrieve(ClientProfile(industry="restaurant"), [SectionId.fire], k=3) == []


def test_soft_delete_keeps_the_record_but_removes_it_from_memory(fake_llm):
    memory.store(_case("C-0001"))
    memory.store(_case("C-0002", industry="bakery"))

    deleted = memory.delete_case("C-0001", "Cameron", "Duplicate of C-0002.")

    assert deleted.deleted_by == "Cameron" and deleted.deleted_reason == "Duplicate of C-0002."
    assert deleted.deleted_at
    assert [c.case_id for c in memory.all_cases()] == ["C-0002"]
    assert [c.case_id for c in memory.deleted_cases()] == ["C-0001"]
    assert memory.get_case("C-0001") is not None, "the report stays readable"
    assert memory.retrieve(ClientProfile(industry="restaurant"), [SectionId.fire], k=3) == [] or \
        all(c.case_id != "C-0001" for c in memory.active_cases())
    assert memory.next_case_id() == "C-0003", "IDs never reuse a deleted case's number"
    assert memory.delete_case("C-9999", "x", "y") is None
