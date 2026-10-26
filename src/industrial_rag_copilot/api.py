from __future__ import annotations

from typing import Any, Dict, List
from fastapi import FastAPI
from pydantic import BaseModel
from industrial_rag_copilot.models import (
    CopilotQueryRequest,
    GroundedMaintenanceResponse,
    SecurityClearance,
    SopDocumentChunk,
)
from industrial_rag_copilot.service import IndustrialMaintenanceCopilotService
from industrial_rag_copilot.vision_defect_triage import (
    EquipmentTelemetrySnapshot,
    VisionTelemetryTriageResult,
)


class TelemetryTriageRequest(BaseModel):
    snapshot: EquipmentTelemetrySnapshot
    user_clearance: SecurityClearance = SecurityClearance.MAINTENANCE_ENGINEER_L2


class TelemetryTriageEnvelope(BaseModel):
    triage: VisionTelemetryTriageResult
    maintenance_plan: GroundedMaintenanceResponse


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Industrial Hybrid RAG & Maintenance Copilot API",
        version="1.1.0",
        description="KVKK/GDPR PII-Redacting Hybrid RAG (BM25 + Dense RRF), SQLite Audit Store, Vision/Telemetry Defect Triage & ISO 45001 LOTO Guardrails",
    )
    copilot_service = IndustrialMaintenanceCopilotService()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "enterprise-industrial-rag-maintenance-copilot",
            "indexed_sop_chunks": len(copilot_service.corpus),
        }

    @app.post("/api/v1/copilot/query", response_model=GroundedMaintenanceResponse)
    def query_copilot(request: CopilotQueryRequest) -> GroundedMaintenanceResponse:
        return copilot_service.answer_query(request)

    @app.post("/api/v1/copilot/triage-telemetry", response_model=TelemetryTriageEnvelope)
    def triage_telemetry(request: TelemetryTriageRequest) -> TelemetryTriageEnvelope:
        triage_res, plan = copilot_service.triage_equipment_telemetry(
            snapshot=request.snapshot,
            user_clearance=request.user_clearance,
        )
        return TelemetryTriageEnvelope(triage=triage_res, maintenance_plan=plan)

    @app.post("/api/v1/copilot/sop")
    def ingest_sop(chunk: SopDocumentChunk) -> dict[str, Any]:
        total = copilot_service.ingest_sop_chunk(chunk)
        return {"status": "indexed", "doc_id": chunk.doc_id, "total_chunks": total}

    @app.get("/api/v1/copilot/audit-logs")
    def list_audit_logs(limit: int = 25) -> List[Dict[str, Any]]:
        return copilot_service.get_audit_logs(limit=limit)

    return app


app = create_app()
