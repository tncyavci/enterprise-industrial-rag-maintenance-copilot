from __future__ import annotations

from fastapi import FastAPI
from industrial_rag_copilot.models import CopilotQueryRequest, GroundedMaintenanceResponse
from industrial_rag_copilot.service import IndustrialMaintenanceCopilotService


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Industrial Hybrid RAG & Maintenance Copilot API",
        version="1.0.0",
        description="KVKK/GDPR PII-Redacting Hybrid RAG (BM25 + Dense RRF) with ISO 45001 LOTO & Citation Guardrails",
    )
    copilot_service = IndustrialMaintenanceCopilotService()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "enterprise-industrial-rag-maintenance-copilot"}

    @app.post("/api/v1/copilot/query", response_model=GroundedMaintenanceResponse)
    def query_copilot(request: CopilotQueryRequest) -> GroundedMaintenanceResponse:
        return copilot_service.answer_query(request)

    return app


app = create_app()
