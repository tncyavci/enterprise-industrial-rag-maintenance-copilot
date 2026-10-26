"""FastMCP Server exposing KVKK-safe Industrial Hybrid RAG & Telemetry Defect Triage tools."""

from __future__ import annotations

from typing import Any, Dict
from industrial_rag_copilot.models import CopilotQueryRequest, SecurityClearance
from industrial_rag_copilot.service import IndustrialMaintenanceCopilotService
from industrial_rag_copilot.vision_defect_triage import EquipmentTelemetrySnapshot

_service = IndustrialMaintenanceCopilotService()


def query_industrial_sop_copilot(
    query: str,
    user_clearance: str = "MAINTENANCE_ENGINEER_L2",
    top_k: int = 3,
) -> Dict[str, Any]:
    """Query the KVKK-redacting Hybrid RAG (BM25 + RRF) SOP engine with RBAC and LOTO guardrails."""
    response = _service.answer_query(
        CopilotQueryRequest(
            query=query,
            user_clearance=SecurityClearance(user_clearance),
            top_k=top_k,
        )
    )
    return response.model_dump()


def triage_station_telemetry(
    station_id: str,
    ocr_nameplate_text: str = "",
    servo_vibration_mm_s: float = 1.2,
    hv_isolation_ohm_per_volt: float = 550.0,
    paint_booth_pressure_pa: float = 120.0,
    user_clearance: str = "MAINTENANCE_ENGINEER_L2",
) -> Dict[str, Any]:
    """Triage industrial station OCR nameplate text and live sensor telemetry against SOP thresholds."""
    snapshot = EquipmentTelemetrySnapshot(
        station_id=station_id,
        ocr_nameplate_text=ocr_nameplate_text,
        servo_vibration_mm_s=servo_vibration_mm_s,
        hv_isolation_ohm_per_volt=hv_isolation_ohm_per_volt,
        paint_booth_pressure_pa=paint_booth_pressure_pa,
    )
    triage_res, plan = _service.triage_equipment_telemetry(
        snapshot=snapshot,
        user_clearance=SecurityClearance(user_clearance),
    )
    return {
        "triage": triage_res.model_dump(),
        "maintenance_plan": plan.model_dump(),
    }


if __name__ == "__main__":
    try:
        from fastmcp import FastMCP

        mcp = FastMCP("Enterprise-Industrial-RAG-Maintenance-Copilot")
        mcp.tool()(query_industrial_sop_copilot)
        mcp.tool()(triage_station_telemetry)
        mcp.run()
    except ImportError:
        raise SystemExit("Install fastmcp (`pip install -e '.[mcp]'`) to run the MCP server.")
