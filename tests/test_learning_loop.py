"""End-to-end test of the loop with a fake LLM: needs -> per-section assess ->
guardrails -> approve -> reflect -> the next assessment's prompt contains what
was learned, scoped to the right section."""

import threading
from pathlib import Path

from app import guardrails, memory
from app.assess import assess_sections
from app.ingest_chats import IngestedCase, ingest_file
from app.memory import _PlaybookUpdate, _RetrievalPick
from app.models import (CaseRecord, ClientProfile, Correction, Requirement,
                        RiskFinding, SectionAssessment, SectionNeed, Severity)
from app.sections import SectionId

RAW = (
    "Business name: Testaurant\n"
    "Industry: restaurant\n"
    "Fire cover: Yes\n"
    "Gas kitchen — no gas certificate of conformity on file since the refit.\n"
    "Delivery scooters parked on the street overnight.\n"
)

PROFILE = ClientProfile(business_name="Testaurant", industry="restaurant",
                        covers_requested=["Fire"], summary="Restaurant with a gas kitchen; covers: Fire")


def _need(section, reason="stated in the submission"):
    return SectionNeed(section=section, requirement=Requirement.required, reason=reason)


def _finding(**overrides) -> RiskFinding:
    base = dict(
        factor_name="uncertified_gas_installation", section=SectionId.fire,
        severity=Severity.medium,
        evidence_quote="no gas certificate of conformity on file",
        reasoning="Uncertified gas installation after a refit.", confidence=0.9,
    )
    base.update(overrides)
    return RiskFinding(**base)


def test_one_call_per_required_section_and_guardrails_drop_hallucinations(fake_llm):
    fake_llm.register(SectionAssessment, SectionAssessment(
        findings=[_finding(),
                  _finding(factor_name="asbestos_roof", evidence_quote="roof is asbestos sheeting")],
    ))
    draft, engine = assess_sections(RAW, PROFILE, [_need(SectionId.fire), _need(SectionId.motor)])
    assert engine == "fake"
    section_calls = [c for c in fake_llm.calls if c[0] == "SectionAssessment"]
    assert len(section_calls) == 2
    # Findings are stamped with the section they were assessed under.
    assert {f.section for f in draft.findings} == {SectionId.fire, SectionId.motor}

    result = guardrails.apply(draft, RAW)
    dropped_names = {f.factor_name for f, _ in result.dropped}
    assert dropped_names == {"asbestos_roof"}  # the invented quote, in both sections


def test_section_calls_run_concurrently(fake_llm):
    # Each call blocks until the other arrives — passes only if both sections
    # are genuinely in flight at the same time.
    barrier = threading.Barrier(2, timeout=5)

    def respond(system, user):
        barrier.wait()
        return SectionAssessment(findings=[_finding()])

    fake_llm.register(SectionAssessment, respond)
    draft, _ = assess_sections(RAW, PROFILE, [_need(SectionId.fire), _need(SectionId.motor)])
    assert {f.section for f in draft.findings} == {SectionId.fire, SectionId.motor}


def test_not_applicable_sections_are_not_assessed(fake_llm):
    fake_llm.register(SectionAssessment, SectionAssessment(findings=[_finding()]))
    needs = [
        _need(SectionId.fire),
        SectionNeed(section=SectionId.motor, requirement=Requirement.not_applicable, reason="no vehicles"),
        SectionNeed(section=SectionId.money, requirement=Requirement.not_applicable, reason="no cash handled"),
    ]
    assess_sections(RAW, PROFILE, needs)
    assert len([c for c in fake_llm.calls if c[0] == "SectionAssessment"]) == 1


def test_correction_reaches_the_next_assessment_prompt_for_its_section(fake_llm):
    # --- round 1: assess, reviewer bumps severity, approve ------------------
    fake_llm.register(SectionAssessment, SectionAssessment(findings=[_finding()]))
    draft, _ = assess_sections(RAW, PROFILE, [_need(SectionId.fire)])
    result = guardrails.apply(draft, RAW)

    approved = [f.model_copy(update={"severity": Severity.high}) for f in result.findings]
    case = CaseRecord(
        case_id=memory.next_case_id(), created_at="2026-07-09T10:00:00", source="assessment",
        client_profile=PROFILE, summary=PROFILE.summary,
        draft_findings=result.findings, approved_findings=approved,
        corrections=[Correction(type="severity_changed",
                                factor_name="uncertified_gas_installation",
                                detail="medium -> high", note="Never medium without a certificate.")],
        final_band=guardrails.band_for_findings(approved),
    )
    memory.store(case)

    # --- gate 3: the underwriter accepts the proposed lesson ----------------
    lesson = "## PB-001 · [fire] food service — gas installations\nAbsence of a certificate is HIGH.\nSupporting cases: C-0001\n"
    fake_llm.register(_PlaybookUpdate, _PlaybookUpdate(
        playbook_markdown=memory.PLAYBOOK_STUB + "\n" + lesson, change_note="Added PB-001."))
    proposal = memory.propose_reflection(case)
    assert proposal is not None
    memory.save_playbook(proposal.proposed_playbook)

    # --- round 2: the Fire prompt must carry the lesson and the precedent ---
    fake_llm.register(_RetrievalPick, _RetrievalPick(case_ids=["C-0001"]))
    fake_llm.register(SectionAssessment, SectionAssessment(
        findings=[_finding(severity=Severity.high,
                           precedent_case_ids=["C-0001"], playbook_rule_ids=["PB-001"])],
    ))
    draft2, _ = assess_sections(RAW, PROFILE, [_need(SectionId.fire)])

    model_name, tier, system, user = fake_llm.calls[-1]
    assert model_name == "SectionAssessment" and tier == "main"
    assert "PB-001" in system, "playbook lesson must be in the system prompt"
    assert "Case C-0001" in user, "precedent case must be in the user message"
    assert draft2.findings[0].playbook_rule_ids == ["PB-001"]


def test_a_fire_lesson_is_structurally_unable_to_reach_a_motor_assessment(fake_llm):
    memory.save_playbook(
        memory.PLAYBOOK_STUB
        + "\n## PB-001 · [fire] gas installations\nAbsence of a certificate is HIGH.\nSupporting cases: C-0001\n"
    )
    fake_llm.register(SectionAssessment, SectionAssessment(findings=[]))
    assess_sections(RAW, PROFILE, [_need(SectionId.motor)])
    _, _, system, _ = fake_llm.calls[-1]
    assert "PB-001" not in system


def test_ingest_stores_a_provisional_case_and_never_touches_the_playbook(fake_llm):
    playbook_before = memory.load_playbook()
    fake_llm.register(IngestedCase, IngestedCase(
        client_profile=PROFILE, summary=PROFILE.summary,
        approved_findings=[_finding(severity=Severity.high)],
    ))
    case = ingest_file(Path("sample_data/chats/chat_01_restaurant.md"))
    assert case is not None
    assert case.source == "chat_ingestion"
    assert case.provisional, "ingested cases must wait for human confirmation"
    assert case.final_band == "Elevated"
    assert memory.get_case(case.case_id) is not None
    assert memory.load_playbook() == playbook_before, "SOLUTION_DESIGN §4.4: no ungated playbook write"


def test_ingest_skips_chats_without_decisions(fake_llm):
    fake_llm.register(IngestedCase, IngestedCase(
        client_profile=PROFILE, approved_findings=[], contains_risk_decision=False))
    assert ingest_file(Path("sample_data/chats/chat_01_restaurant.md")) is None
