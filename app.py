"""Interactive Streamlit Enterprise Maintenance & KVKK Compliance Console."""

from __future__ import annotations

import streamlit as st
from industrial_rag_copilot.models import CopilotQueryRequest, SecurityClearance
from industrial_rag_copilot.service import IndustrialMaintenanceCopilotService
from industrial_rag_copilot.vision_defect_triage import EquipmentTelemetrySnapshot

st.set_page_config(
    page_title="Enterprise Industrial Hybrid RAG Copilot",
    layout="wide",
)

if "copilot_service" not in st.session_state:
    st.session_state.copilot_service = IndustrialMaintenanceCopilotService()

service: IndustrialMaintenanceCopilotService = st.session_state.copilot_service

st.title("Enterprise Industrial Hybrid RAG & Maintenance Copilot")
st.caption(
    "KVKK/GDPR PII-Redacting Hybrid Search (Okapi BM25 + Dense Trigram RRF) • RBAC Clearance Gate • ISO 45001 LOTO Guardrails"
)

col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("1. Operator Query / Maintenance Ticket")
    clearance = st.selectbox(
        "Security Clearance Tier (RBAC)",
        options=[c.value for c in SecurityClearance],
        index=2,
    )
    raw_query = st.text_area(
        "Maintenance Ticket / Transcript (PII is automatically redacted before indexing)",
        value="Operatör TCKN 10000000146 (Tel: +90 532 111 22 33, Plaka: 16 TFS 45): BIW kaynak robotunda SRVO-053 hatası ve SKU-HD-8841 harmonik redüktör aşırı tork uyarısı var.",
        height=110,
    )
    if st.button("Execute Grounded Hybrid RAG Query", type="primary"):
        result = service.answer_query(
            CopilotQueryRequest(
                query=raw_query,
                user_clearance=SecurityClearance(clearance),
                top_k=3,
            )
        )
        st.markdown(f"**Sanitized Query:** `{result.sanitized_query}`")
        if result.pii_redactions:
            st.warning(
                "KVKK PII Redactions Applied: "
                + ", ".join(f"{r.entity_type} ({r.redacted_count})" for r in result.pii_redactions)
            )
        if result.lockout_tagout_mandatory:
            st.error(f"ISO 45001 LOCKOUT/TAGOUT MANDATORY • Urgency: {result.urgency.value}")
        else:
            st.info(f"Urgency: {result.urgency.value}")

        st.markdown("#### Recommended Verbatim SOP Steps")
        for step in result.recommended_steps:
            st.write(f"- {step}")

        if result.referenced_part_numbers:
            st.markdown("**Referenced Part SKUs:** " + ", ".join(f"`{p}`" for p in result.referenced_part_numbers))

with col_right:
    st.subheader("2. Live Sensor & Vision OCR Defect Triage")
    station = st.text_input("Station ID", value="BIW-CELL-04")
    ocr_text = st.text_input("Camera OCR Nameplate / Barcode Text", value="FANUC-AX3 SKU-HD-8841")
    vib = st.slider("Servo Vibration RMS (mm/s)", 0.0, 15.0, 8.4, 0.1)
    hv_iso = st.slider("HV Battery Isolation Resistance (Ohm/V)", 20.0, 600.0, 520.0, 10.0)

    if st.button("Run Sensor & Vision Triage"):
        triage_res, plan = service.triage_equipment_telemetry(
            snapshot=EquipmentTelemetrySnapshot(
                station_id=station,
                ocr_nameplate_text=ocr_text,
                servo_vibration_mm_s=vib,
                hv_isolation_ohm_per_volt=hv_iso,
            ),
            user_clearance=SecurityClearance(clearance),
        )
        st.json(triage_res.model_dump())

st.divider()
st.subheader("3. Immutable KVKK & RBAC Compliance Audit Trail (SQLite)")
st.dataframe(service.get_audit_logs(limit=15), use_container_width=True)
