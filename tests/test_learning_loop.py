"""End-to-end test of the loop with a fake LLM: assess -> guardrails ->
approve -> reflect -> the next assessment's prompt contains what was learned."""

from pathlib import Path

from app import guardrails, memory
from app.assess import assess
from app.ingest_chats import IngestedCase, ingest_file
from app.memory import _PlaybookUpdate, _RetrievalPick
from app.models import (CaseRecord, ClientProfile, Correction,
                        RiskAssessmentDraft, RiskFinding, Severity)

RAW = (
    "Business name: Testaurant\n"
    "Industry: restaurant\n"
    "Fire cover: Yes\n"
    "Gas kitchen — no gas certificate of conformity on file since the refit.\n"
)

PROFILE = ClientProfile(business_name="Testaurant", industry="restaurant",
                        covers_requested=["Fire"], summary="Restaurant with a gas kitchen; covers: Fire")


def _finding(**overrides) -> RiskFinding:
    base = dict(
        factor_name="uncertified_gas_installation", section="Fire",
        severity=Severity.medium, suggested_points=10,
        evidence_quote="no gas certificate of conformity on file",
        reasoning="Uncertified gas installation after a refit.", confidence=0.9,
    )
    base.update(overrides)
    return RiskFinding(**base)


def test_assess_runs_and_guardrails_drop_hallucinations(fake_llm):
    fake_llm.register(ClientProfile, PROFILE)
    fake_llm.register(RiskAssessmentDraft, RiskAssessmentDraft(
        client_profile=PROFILE,
        findings=[_finding(),
                  _finding(factor_name="asbestos_roof", evidence_quote="roof is asbestos sheeting")],
    ))
    draft, engine = assess(RAW)
    assert engine == "fake"
    result = guardrails.apply(draft, RAW)
    assert [f.factor_name for f in result.findings] == ["uncertified_gas_installation"]
    assert len(result.dropped) == 1  # the invented asbestos quote


def test_correction_reaches_the_next_assessment_prompt(fake_llm):
    # --- round 1: assess, reviewer bumps severity, approve, reflect ---------
    fake_llm.register(ClientProfile, PROFILE)
    fake_llm.register(RiskAssessmentDraft, RiskAssessmentDraft(client_profile=PROFILE, findings=[_finding()]))
    draft, _ = assess(RAW)
    result = guardrails.apply(draft, RAW)

    approved = [f.model_copy(update={"severity": Severity.high, "suggested_points": 18})
                for f in result.findings]
    case = CaseRecord(
        case_id=memory.next_case_id(), created_at="2026-07-09T10:00:00", source="assessment",
        client_profile=PROFILE, summary=PROFILE.summary,
        draft_findings=result.findings, approved_findings=approved,
        corrections=[Correction(type="severity_changed",
                                factor_name="uncertified_gas_installation", detail="medium -> high")],
        final_score=18, final_band="Moderate",
    )
    memory.store(case)
    lesson = "## PB-001 · food service — gas installations\nAbsence of a certificate is HIGH.\nSupporting cases: C-0001\n"
    fake_llm.register(_PlaybookUpdate, _PlaybookUpdate(
        playbook_markdown=memory.PLAYBOOK_STUB + "\n" + lesson, change_note="Added PB-001."))
    assert memory.reflect(case) == "Added PB-001."

    # --- round 2: the new prompt must carry the lesson and the precedent ----
    fake_llm.register(_RetrievalPick, _RetrievalPick(case_ids=["C-0001"]))
    fake_llm.register(RiskAssessmentDraft, RiskAssessmentDraft(
        client_profile=PROFILE,
        findings=[_finding(severity=Severity.high, suggested_points=18,
                           precedent_case_ids=["C-0001"], playbook_rule_ids=["PB-001"])],
    ))
    draft2, _ = assess(RAW)

    model_name, tier, system, user = fake_llm.calls[-1]  # the main assessment call
    assert model_name == "RiskAssessmentDraft" and tier == "main"
    assert "PB-001" in system, "playbook lesson must be in the system prompt"
    assert "Case C-0001" in user, "precedent case must be in the user message"
    assert draft2.findings[0].playbook_rule_ids == ["PB-001"]


def test_ingest_stores_a_chat_case(fake_llm):
    fake_llm.register(IngestedCase, IngestedCase(
        client_profile=PROFILE, summary=PROFILE.summary,
        approved_findings=[_finding(severity=Severity.high, suggested_points=18)],
    ))
    case = ingest_file(Path("sample_data/chats/chat_01_restaurant.md"))
    assert case is not None
    assert case.source == "chat_ingestion"
    assert case.final_band == "Moderate"
    assert memory.get_case(case.case_id) is not None


def test_ingest_skips_chats_without_decisions(fake_llm):
    fake_llm.register(IngestedCase, IngestedCase(
        client_profile=PROFILE, approved_findings=[], contains_risk_decision=False))
    assert ingest_file(Path("sample_data/chats/chat_01_restaurant.md")) is None
