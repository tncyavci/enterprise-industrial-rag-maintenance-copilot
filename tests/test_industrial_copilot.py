from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from industrial_rag_copilot.api import create_app
from industrial_rag_copilot.models import (
    CopilotQueryRequest,
    GroundedMaintenanceResponse,
    MaintenanceUrgency,
    SecurityClearance,
)
from industrial_rag_copilot.pii_redactor import KvkkPiiRedactor
from industrial_rag_copilot.service import IndustrialMaintenanceCopilotService


def test_kvkk_pii_redactor_masks_tckn_iban_phone_email_and_plate() -> None:
    redactor = KvkkPiiRedactor()
    raw = (
        "Operator TCKN 10000000146 reported fault SRVO-053 on vehicle 16 TFS 45. "
        "Contact +90 532 111 22 33 or op@factory.com.tr. IBAN TR330006100519786457841326."
    )
    sanitized, events = redactor.sanitize(raw)

    assert "10000000146" not in sanitized
    assert "TR330006100519786457841326" not in sanitized
    assert "532 111 22 33" not in sanitized
    assert "op@factory.com.tr" not in sanitized
    assert "16 TFS 45" not in sanitized
    assert "[REDACTED_TCKN]" in sanitized
    assert "[REDACTED_TR_IBAN]" in sanitized
    assert "[REDACTED_TR_PHONE]" in sanitized
    assert "[REDACTED_EMAIL]" in sanitized
    assert "[REDACTED_TR_PLATE]" in sanitized
    assert len(events) == 5
    assert redactor.is_valid_tckn_checksum("10000000146") is True
    assert redactor.is_valid_tckn_checksum("10000000147") is False


def test_hybrid_rrf_retrieves_exact_sku_and_enforces_loto_guardrail() -> None:
    service = IndustrialMaintenanceCopilotService()
    req = CopilotQueryRequest(
        query="Welding robot error SRVO-053 harmonic drive SKU-HD-8841",
        user_clearance=SecurityClearance.MAINTENANCE_ENGINEER_L2,
        top_k=2,
    )
    res = service.answer_query(req)

    assert res.abstained_due_to_insufficient_evidence is False
    assert res.lockout_tagout_mandatory is True
    assert res.urgency == MaintenanceUrgency.IMMEDIATE_LINE_STOP
    assert "SKU-HD-8841" in res.referenced_part_numbers
    assert any(c.doc_id == "SOP-ROBOTICS-001" for c in res.citations)


def test_rbac_clearance_blocks_restricted_hv_battery_sop_for_l1_operator() -> None:
    service = IndustrialMaintenanceCopilotService()
    req_l1 = CopilotQueryRequest(
        query="P0AA6 MSD-PLUG-900 SKU-HVC-450 isolation fault",
        user_clearance=SecurityClearance.OPERATOR_L1,
        top_k=3,
    )
    res_l1 = service.answer_query(req_l1)
    assert all(c.doc_id != "SOP-BATTERY-HV-002" for c in res_l1.citations)

    req_l3 = CopilotQueryRequest(
        query="P0AA6 MSD-PLUG-900 SKU-HVC-450 isolation fault",
        user_clearance=SecurityClearance.RESTRICTED_SAFETY_L3,
        top_k=3,
    )
    res_l3 = service.answer_query(req_l3)
    assert any(c.doc_id == "SOP-BATTERY-HV-002" for c in res_l3.citations)


def test_pydantic_guardrail_rejects_uncited_response() -> None:
    with pytest.raises(ValidationError):
        GroundedMaintenanceResponse(
            sanitized_query="How to fix welding robot?",
            pii_redactions=[],
            urgency=MaintenanceUrgency.ROUTINE,
            lockout_tagout_mandatory=False,
            recommended_steps=["Replace the motor immediately."],
            referenced_part_numbers=[],
            citations=[],
            abstained_due_to_insufficient_evidence=False,
        )


def test_fastapi_endpoints_return_grounded_response() -> None:
    client = TestClient(create_app())
    health = client.get("/health")
    assert health.status_code == 200

    resp = client.post(
        "/api/v1/copilot/query",
        json={
            "query": "Operator 10000000146 asks about SRVO-053 and SKU-HD-8841",
            "user_clearance": "MAINTENANCE_ENGINEER_L2",
            "top_k": 2,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "[REDACTED_TCKN]" in payload["sanitized_query"]
    assert payload["lockout_tagout_mandatory"] is True
    assert len(payload["citations"]) >= 1


def test_vision_telemetry_triage_and_sqlite_audit_trail() -> None:
    client = TestClient(create_app())
    triage_resp = client.post(
        "/api/v1/copilot/triage-telemetry",
        json={
            "snapshot": {
                "station_id": "BIW-WELD-09",
                "ocr_nameplate_text": "HARMONIC REDUCER SKU-HD-8841",
                "servo_vibration_mm_s": 9.2,
                "hv_isolation_ohm_per_volt": 540.0,
                "paint_booth_pressure_pa": 110.0,
            },
            "user_clearance": "MAINTENANCE_ENGINEER_L2",
        },
    )
    assert triage_resp.status_code == 200
    body = triage_resp.json()
    assert body["triage"]["anomaly_detected"] is True
    assert "SRVO-053" in body["triage"]["detected_fault_codes"]
    assert "SKU-HD-8841" in body["triage"]["extracted_skus"]
    assert body["maintenance_plan"]["lockout_tagout_mandatory"] is True

    audit_resp = client.get("/api/v1/copilot/audit-logs")
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    assert len(logs) >= 1
    assert logs[0]["loto_mandatory"] is True

