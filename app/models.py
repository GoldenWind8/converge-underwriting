"""
Data model for the self-learning risk assessment (docs/SOLUTION_DESIGN.md §3,
consolidated per docs/CONSOLIDATION_PLAN.md).

The flow's shapes, in pipeline order:

- SectionNeed / NeedsDetermination   which of the 18 cover sections this
                                     business needs — produced by the model,
                                     confirmed by the underwriter (human gate 1).
- RiskFinding                        one risk factor the LLM proposes within a
                                     section. Free about *content*, on rails
                                     about *shape*: verbatim evidence, a
                                     standardised severity, driver slugs.
- RiskAssessmentDraft                what an assessment run produces, before
                                     human review (gate 2).
- DriverGroup                        one underlying weakness surfacing under
                                     two or more sections — computed, no model.
- CaseRecord                         one approved case, the unit of memory.
                                     Only records a human signed off ever
                                     become non-provisional CaseRecords.

There is deliberately no numeric score anywhere: severity is a standardised
categorical scale, and the case band is derived from the severity profile by
deterministic code in guardrails.py. Nothing the system emits can be read as
a price or a rating.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional, Set

from pydantic import BaseModel, Field, PrivateAttr, field_validator

from .sections import MotorSubType, SectionId, normalise_slugs


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    severe = "severe"


SEVERITY_ORDER = {Severity.low: 0, Severity.medium: 1, Severity.high: 2, Severity.severe: 3}


class Requirement(str, Enum):
    required = "required"
    consider = "consider"
    not_applicable = "not-applicable"


class ClientProfile(BaseModel):
    """Slim profile — just enough to file, retrieve, and report on a case."""

    business_name: Optional[str] = Field(None, description="Name of the business.")
    industry: Optional[str] = Field(None, description="Industry or trade, e.g. 'restaurant', 'panel beater'.")
    employees: Optional[int] = Field(None, description="Number of employees, if stated.")
    covers_requested: List[str] = Field(default_factory=list, description="Covers applied for, e.g. ['Fire', 'Public Liability'].")
    summary: str = Field("", description="One or two sentences describing the client and its risk character; used to retrieve similar past cases.")


class SectionNeed(BaseModel):
    """One row of the needs determination: does this business need this section?"""

    section: SectionId = Field(..., description="The cover section id, exactly as listed in the system prompt.")
    requirement: Requirement
    reason: str = Field("", description="One line, grounded in the submission. Name the fact that decides it.")
    motor_sub_type: Optional[MotorSubType] = Field(
        None, description="Only for the motor section, when required or worth considering: the sub-type that fits the submission.")


class NeedsDetermination(BaseModel):
    business_note: str = Field("", description="One sentence on what this business is and does, as read from the submission.")
    needs: List[SectionNeed] = Field(default_factory=list, description="Exactly one entry per cover section, in the order listed.")


class RiskFinding(BaseModel):
    factor_name: str = Field(..., description="Short snake_case name for the risk factor, e.g. 'uncertified_gas_installation'.")
    section: SectionId = Field(..., description="The cover section this finding was assessed under.")
    severity: Severity = Field(..., description="Standardised scale: low, medium, high, or severe.")
    assessment_note: str = Field("", description="One line naming the reference class the judgement was made against, e.g. 'below standard for a food-production occupancy'. Narrative only — never a number.")
    evidence_quote: str = Field(..., description="Verbatim text copied from the source document that evidences this risk.")
    reasoning: str = Field(..., description="Why this is a risk for this client.")
    drivers: List[str] = Field(default_factory=list, description="One to three kebab-case slugs naming the underlying facts about the business that drive this finding.")
    precedent_case_ids: List[str] = Field(default_factory=list, description="IDs of retrieved past cases that informed this finding. Empty = novel.")
    playbook_rule_ids: List[str] = Field(default_factory=list, description="IDs of playbook rules (PB-xxx) that informed this finding.")
    confidence: float = Field(0.5, description="0-1. Low confidence forces a human referral.")

    @field_validator("drivers", mode="before")
    @classmethod
    def _normalise_drivers(cls, value):
        return normalise_slugs(value)


class SectionAssessment(BaseModel):
    """What one per-section model call returns."""

    memory_note: str = Field("", description="One sentence on how playbook rules and precedents shaped this section's findings. If they did not, say so.")
    findings: List[RiskFinding] = Field(default_factory=list)


class RiskAssessmentDraft(BaseModel):
    client_profile: ClientProfile
    findings: List[RiskFinding] = Field(default_factory=list)
    overall_notes: List[str] = Field(default_factory=list, description="Ambiguities, missing information, or general observations.")

    # Runtime-only provenance: the exact context supplied to the assessment model.
    # These are deliberately excluded from the model schema and persisted record.
    _retrieved_case_ids: Optional[Set[str]] = PrivateAttr(default=None)
    _available_rule_ids: Optional[Set[str]] = PrivateAttr(default=None)


class DriverGroup(BaseModel):
    """One underlying weakness surfacing under two or more sections."""

    class Hit(BaseModel):
        section: SectionId
        factor_name: str
        severity: Severity

    driver: str
    hits: List[Hit] = Field(default_factory=list)
    section_count: int = 0


class Correction(BaseModel):
    """One human edit, draft -> approved. The raw material for reflection."""

    type: Literal["added", "removed", "severity_changed"]
    factor_name: str
    detail: str = ""
    note: str = ""  # the reviewer's own words on *why* — remembered verbatim


class CaseRecord(BaseModel):
    case_id: str
    created_at: str  # ISO timestamp
    source: Literal["assessment", "chat_ingestion"]
    client_profile: ClientProfile
    summary: str  # short description used for retrieval
    needs: List[SectionNeed] = Field(default_factory=list)  # the confirmed needs table
    draft_findings: List[RiskFinding] = Field(default_factory=list)
    approved_findings: List[RiskFinding] = Field(default_factory=list)
    corrections: List[Correction] = Field(default_factory=list)
    driver_groups: List[DriverGroup] = Field(default_factory=list)
    final_band: str = "Low"
    # Chat-ingested cases stay provisional — invisible to retrieval — until a
    # human confirms them (docs/CONSOLIDATION_PLAN.md §7.3).
    provisional: bool = False
