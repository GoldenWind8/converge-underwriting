"""
Data model for the self-learning risk assessment (docs/SOLUTION_DESIGN.md §3).

Three ideas, three models:

- RiskFinding        one risk factor the LLM (or mock engine) proposes. The LLM
                     is free about *content* (it names its own factors) but on
                     rails about *shape* — every finding must carry verbatim
                     evidence and cite what informed it.
- RiskAssessmentDraft  what an assessment run produces, before human review.
- CaseRecord         one approved case — the unit of memory. Only records a
                     human signed off ever become CaseRecords.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional, Set

from pydantic import BaseModel, Field, PrivateAttr


class Severity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"


class ClientProfile(BaseModel):
    """Slim profile — just enough to file, retrieve, and report on a case."""

    business_name: Optional[str] = Field(None, description="Name of the business.")
    industry: Optional[str] = Field(None, description="Industry or trade, e.g. 'restaurant', 'panel beater'.")
    employees: Optional[int] = Field(None, description="Number of employees, if stated.")
    covers_requested: List[str] = Field(default_factory=list, description="Covers applied for, e.g. ['Fire', 'Public Liability'].")
    summary: str = Field("", description="One or two sentences describing the client and its risk character; used to retrieve similar past cases.")


class RiskFinding(BaseModel):
    factor_name: str = Field(..., description="Short snake_case name for the risk factor, e.g. 'uncertified_gas_installation'.")
    section: str = Field(..., description="Cover it affects: Fire, Business Interruption, Public Liability, or General.")
    severity: Severity
    suggested_points: int = Field(..., description="Risk points. Guardrails cap these per severity tier.")
    evidence_quote: str = Field(..., description="Verbatim text copied from the source document that evidences this risk.")
    reasoning: str = Field(..., description="Why this is a risk for this client.")
    precedent_case_ids: List[str] = Field(default_factory=list, description="IDs of retrieved past cases that informed this finding. Empty = novel.")
    playbook_rule_ids: List[str] = Field(default_factory=list, description="IDs of playbook rules (PB-xxx) that informed this finding.")
    confidence: float = Field(0.5, description="0-1. Low confidence forces a human referral.")


class RiskAssessmentDraft(BaseModel):
    client_profile: ClientProfile
    findings: List[RiskFinding] = Field(default_factory=list)
    overall_notes: List[str] = Field(default_factory=list, description="Ambiguities, missing information, or general observations.")

    # Runtime-only provenance: the exact context supplied to the assessment model.
    # These are deliberately excluded from the model schema and persisted record.
    _retrieved_case_ids: Optional[Set[str]] = PrivateAttr(default=None)
    _available_rule_ids: Optional[Set[str]] = PrivateAttr(default=None)


class Correction(BaseModel):
    """One human edit, draft -> approved. The raw material for reflection."""

    type: Literal["added", "removed", "severity_changed", "points_changed"]
    factor_name: str
    detail: str = ""


class CaseRecord(BaseModel):
    case_id: str
    created_at: str  # ISO timestamp
    source: Literal["assessment", "chat_ingestion"]
    client_profile: ClientProfile
    summary: str  # short description used for retrieval
    draft_findings: List[RiskFinding] = Field(default_factory=list)
    approved_findings: List[RiskFinding] = Field(default_factory=list)
    corrections: List[Correction] = Field(default_factory=list)
    final_score: int = 0
    final_band: str = "Low"
