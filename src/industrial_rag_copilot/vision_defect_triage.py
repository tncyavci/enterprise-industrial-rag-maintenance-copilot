from __future__ import annotations

import re
from typing import List, Optional
from pydantic import BaseModel, Field


class EquipmentTelemetrySnapshot(BaseModel):
    station_id: str = Field(..., min_length=2)
    ocr_nameplate_text: str = Field(default="")
    servo_vibration_mm_s: float = Field(default=1.2, ge=0.0)
    hv_isolation_ohm_per_volt: float = Field(default=550.0, ge=0.0)
    paint_booth_pressure_pa: float = Field(default=120.0, ge=0.0)


class VisionTelemetryTriageResult(BaseModel):
    station_id: str
    extracted_skus: List[str]
    detected_fault_codes: List[str]
    synthesized_rag_query: str
    anomaly_detected: bool


class VisionTelemetryDefectTriager:
    """Extracts equipment part numbers (SKUs) and fault codes from noisy industrial
    nameplate OCR text and combines them with sensor telemetry thresholds (ISO 10816
    vibration, ECE R100 HV isolation, HVAC differential pressure) to synthesize a
    precision Hybrid RAG query.
    """

    _SKU_PATTERN = re.compile(r"\b(?:SKU-[A-Z0-9-]+|MSD-PLUG-\d+|ENC-[A-Z0-9-]+)\b", re.IGNORECASE)
    _FAULT_PATTERN = re.compile(r"\b(?:SRVO-\d{3}|P0[A-Z0-9]{3}|U0\d{3})\b", re.IGNORECASE)

    def triage(self, snapshot: EquipmentTelemetrySnapshot) -> VisionTelemetryTriageResult:
        skus = [m.upper() for m in self._SKU_PATTERN.findall(snapshot.ocr_nameplate_text)]
        faults = [m.upper() for m in self._FAULT_PATTERN.findall(snapshot.ocr_nameplate_text)]

        query_terms: List[str] = []
        if snapshot.ocr_nameplate_text.strip():
            query_terms.append(snapshot.ocr_nameplate_text.strip())

        if snapshot.servo_vibration_mm_s >= 7.1:
            if "SRVO-053" not in faults:
                faults.append("SRVO-053")
            query_terms.append("welding robot servo over-torque fault SRVO-053 harmonic drive SKU-HD-8841")

        if snapshot.hv_isolation_ohm_per_volt < 100.0:
            if "P0AA6" not in faults:
                faults.append("P0AA6")
            query_terms.append("high-voltage EV battery isolation fault P0AA6 MSD-PLUG-900 SKU-HVC-450")

        if snapshot.paint_booth_pressure_pa > 240.0:
            query_terms.append("paint booth differential pressure exceeds 240 Pa HEPA filter SKU-FLT-204")

        anomaly = bool(faults) or snapshot.servo_vibration_mm_s >= 7.1 or snapshot.hv_isolation_ohm_per_volt < 100.0 or snapshot.paint_booth_pressure_pa > 240.0
        synthesized_query = " ".join(query_terms) if query_terms else f"Routine inspection for station {snapshot.station_id}"

        return VisionTelemetryTriageResult(
            station_id=snapshot.station_id,
            extracted_skus=list(dict.fromkeys(skus)),
            detected_fault_codes=list(dict.fromkeys(faults)),
            synthesized_rag_query=synthesized_query,
            anomaly_detected=anomaly,
        )
