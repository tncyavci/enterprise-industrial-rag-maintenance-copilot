from __future__ import annotations

from typing import List, Optional
from industrial_rag_copilot.models import (
    CitationEvidence,
    CopilotQueryRequest,
    GroundedMaintenanceResponse,
    MaintenanceUrgency,
    SopDocumentChunk,
)
from industrial_rag_copilot.pii_redactor import KvkkPiiRedactor
from industrial_rag_copilot.retriever import DEFAULT_ENTERPRISE_SOP_CORPUS, HybridRrfRetriever


class IndustrialMaintenanceCopilotService:
    """Orchestrates KVKK PII sanitization, RBAC-filtered Hybrid RRF retrieval, and
    Pydantic v2 citation-grounded response synthesis.
    """

    def __init__(
        self,
        corpus: Optional[List[SopDocumentChunk]] = None,
        redactor: Optional[KvkkPiiRedactor] = None,
    ) -> None:
        self.corpus = corpus if corpus is not None else DEFAULT_ENTERPRISE_SOP_CORPUS
        self.redactor = redactor if redactor is not None else KvkkPiiRedactor()
        self.retriever = HybridRrfRetriever(self.corpus)

    def answer_query(self, request: CopilotQueryRequest) -> GroundedMaintenanceResponse:
        sanitized_query, redaction_events = self.redactor.sanitize(request.query)
        hits = self.retriever.search(
            query=sanitized_query,
            user_clearance=request.user_clearance,
            top_k=request.top_k,
        )

        if not hits:
            return GroundedMaintenanceResponse(
                sanitized_query=sanitized_query,
                pii_redactions=redaction_events,
                urgency=MaintenanceUrgency.ROUTINE,
                lockout_tagout_mandatory=False,
                recommended_steps=[
                    "ABSTAINED: No authorized Standard Operating Procedure (SOP) matched the query at your security clearance level."
                ],
                referenced_part_numbers=[],
                citations=[],
                abstained_due_to_insufficient_evidence=True,
            )

        loto_required = any(chunk.LockoutTagoutRequired for chunk, _ in hits)
        urgency = (
            MaintenanceUrgency.IMMEDIATE_LINE_STOP
            if loto_required
            else MaintenanceUrgency.SCHEDULED_48H
        )

        steps: List[str] = []
        parts: List[str] = []
        citations: List[CitationEvidence] = []

        for chunk, rrf_score in hits:
            steps.append(f"[{chunk.doc_id} §{chunk.clause_id}] {chunk.content}")
            for part in chunk.part_numbers:
                if part not in parts:
                    parts.append(part)
            citations.append(
                CitationEvidence(
                    doc_id=chunk.doc_id,
                    clause_id=chunk.clause_id,
                    verbatim_quote=chunk.content,
                    rrf_score=rrf_score,
                )
            )

        return GroundedMaintenanceResponse(
            sanitized_query=sanitized_query,
            pii_redactions=redaction_events,
            urgency=urgency,
            lockout_tagout_mandatory=loto_required,
            recommended_steps=steps,
            referenced_part_numbers=parts,
            citations=citations,
            abstained_due_to_insufficient_evidence=False,
        )
