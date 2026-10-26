from __future__ import annotations

from typing import Any, Dict, List, Optional
from industrial_rag_copilot.models import (
    CitationEvidence,
    CopilotQueryRequest,
    GroundedMaintenanceResponse,
    MaintenanceUrgency,
    SopDocumentChunk,
)
from industrial_rag_copilot.persistent_store import SqliteEnterpriseKnowledgeStore
from industrial_rag_copilot.pii_redactor import KvkkPiiRedactor
from industrial_rag_copilot.retriever import HybridRrfRetriever
from industrial_rag_copilot.vision_defect_triage import (
    EquipmentTelemetrySnapshot,
    VisionTelemetryDefectTriager,
    VisionTelemetryTriageResult,
)


class IndustrialMaintenanceCopilotService:
    """Orchestrates KVKK PII sanitization, SQLite-backed RBAC Hybrid RRF retrieval,
    Vision/Sensor anomaly triage, and Pydantic v2 citation-grounded response synthesis.
    """

    def __init__(
        self,
        corpus: Optional[List[SopDocumentChunk]] = None,
        redactor: Optional[KvkkPiiRedactor] = None,
        store: Optional[SqliteEnterpriseKnowledgeStore] = None,
    ) -> None:
        self.store = store if store is not None else SqliteEnterpriseKnowledgeStore()
        if corpus is not None:
            for chunk in corpus:
                self.store.upsert_sop_chunk(chunk)
        else:
            self.store.seed_default_corpus_if_empty()

        self.corpus = self.store.load_all_chunks()
        self.redactor = redactor if redactor is not None else KvkkPiiRedactor()
        self.retriever = HybridRrfRetriever(self.corpus)
        self.triager = VisionTelemetryDefectTriager()

    def ingest_sop_chunk(self, chunk: SopDocumentChunk) -> int:
        self.store.upsert_sop_chunk(chunk)
        self.corpus = self.store.load_all_chunks()
        self.retriever = HybridRrfRetriever(self.corpus)
        return len(self.corpus)

    def answer_query(self, request: CopilotQueryRequest) -> GroundedMaintenanceResponse:
        sanitized_query, redaction_events = self.redactor.sanitize(request.query)
        hits = self.retriever.search(
            query=sanitized_query,
            user_clearance=request.user_clearance,
            top_k=request.top_k,
        )

        if not hits:
            response = GroundedMaintenanceResponse(
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
            self.store.record_audit_event(request.user_clearance, response)
            return response

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

        response = GroundedMaintenanceResponse(
            sanitized_query=sanitized_query,
            pii_redactions=redaction_events,
            urgency=urgency,
            lockout_tagout_mandatory=loto_required,
            recommended_steps=steps,
            referenced_part_numbers=parts,
            citations=citations,
            abstained_due_to_insufficient_evidence=False,
        )
        self.store.record_audit_event(request.user_clearance, response)
        return response

    def triage_equipment_telemetry(
        self,
        snapshot: EquipmentTelemetrySnapshot,
        user_clearance: CopilotQueryRequest.__annotations__["user_clearance"],
    ) -> tuple[VisionTelemetryTriageResult, GroundedMaintenanceResponse]:
        triage_result = self.triager.triage(snapshot)
        rag_response = self.answer_query(
            CopilotQueryRequest(
                query=triage_result.synthesized_rag_query,
                user_clearance=user_clearance,
                top_k=3,
            )
        )
        return triage_result, rag_response

    def get_audit_logs(self, limit: int = 25) -> List[Dict[str, Any]]:
        return self.store.list_recent_audit_logs(limit=limit)
