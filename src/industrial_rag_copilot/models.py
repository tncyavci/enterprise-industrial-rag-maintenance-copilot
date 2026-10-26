from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class SecurityClearance(str, Enum):
    PUBLIC = "PUBLIC"
    OPERATOR_L1 = "OPERATOR_L1"
    MAINTENANCE_ENGINEER_L2 = "MAINTENANCE_ENGINEER_L2"
    RESTRICTED_SAFETY_L3 = "RESTRICTED_SAFETY_L3"


class MaintenanceUrgency(str, Enum):
    ROUTINE = "ROUTINE"
    SCHEDULED_48H = "SCHEDULED_48H"
    IMMEDIATE_LINE_STOP = "IMMEDIATE_LINE_STOP"


class SopDocumentChunk(BaseModel):
    doc_id: str = Field(..., pattern=r"^SOP-[A-Z0-9-]+$")
    clause_id: str = Field(..., min_length=2)
    title: str
    equipment_category: str
    required_clearance: SecurityClearance = SecurityClearance.OPERATOR_L1
    LockoutTagoutRequired: bool = False
    content: str = Field(..., min_length=20)
    part_numbers: List[str] = Field(default_factory=list)


class CitationEvidence(BaseModel):
    doc_id: str
    clause_id: str
    verbatim_quote: str = Field(..., min_length=10)
    rrf_score: float = Field(..., ge=0.0)


class PiiRedactionEvent(BaseModel):
    entity_type: str
    redacted_count: int


class CopilotQueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=2000)
    user_clearance: SecurityClearance = SecurityClearance.MAINTENANCE_ENGINEER_L2
    top_k: int = Field(default=3, ge=1, le=10)


class GroundedMaintenanceResponse(BaseModel):
    sanitized_query: str
    pii_redactions: List[PiiRedactionEvent] = Field(default_factory=list)
    urgency: MaintenanceUrgency
    lockout_tagout_mandatory: bool
    recommended_steps: List[str] = Field(..., min_length=1)
    referenced_part_numbers: List[str] = Field(default_factory=list)
    citations: List[CitationEvidence]
    abstained_due_to_insufficient_evidence: bool = False

    @model_validator(mode="after")
    def verify_citation_grounding(self) -> "GroundedMaintenanceResponse":
        if not self.abstained_due_to_insufficient_evidence and len(self.citations) == 0:
            raise ValueError(
                "Hallucination Guardrail Violation: Non-abstained maintenance response must include at least one verbatim SOP citation."
            )
        if self.urgency == MaintenanceUrgency.IMMEDIATE_LINE_STOP and not self.lockout_tagout_mandatory:
            raise ValueError(
                "ISO 45001 / LOTO Guardrail Violation: IMMEDIATE_LINE_STOP procedures must enforce lockout_tagout_mandatory=True."
            )
        return self
