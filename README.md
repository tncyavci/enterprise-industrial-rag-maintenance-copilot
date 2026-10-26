# Enterprise Industrial Hybrid RAG & Maintenance Copilot

**KVKK/GDPR PII-Redacting Hybrid RAG (Okapi BM25 + Character N-Gram Dense Reciprocal Rank Fusion), Role-Based Access Control (RBAC), and ISO 45001 Lockout/Tagout (LOTO) Citation Guardrails built with Python, FastAPI, and Pydantic v2.**

Designed for enterprise manufacturing, automotive R&D, aviation MRO, and regulated banking/corporate IT environments where Standard Operating Procedures (SOPs), maintenance manuals, and incident tickets cannot be sent to external LLMs without strict **Turkish KVKK / GDPR PII sanitization**, **document-level RBAC clearance enforcement**, and **zero-hallucination verbatim citation proofs**.

---

## System Architecture

```mermaid
flowchart LR
    A["Operator Query / Maintenance Ticket"] --> B["KvkkPiiRedactor\n(TCKN, TR IBAN, Phone, Email, Plate)"]
    B --> C["RBAC Clearance Gate\n(PUBLIC / L1 / L2 / L3)"]
    C --> D["Okapi BM25 Lexical Index\n(Exact Part SKUs & Fault Codes)"]
    C --> E["Dense N-Gram Vector Index\n(Semantic / Fuzzy Matching)"]
    D --> F["Reciprocal Rank Fusion (RRF)"]
    E --> F
    F --> G["Pydantic v2 Citation & ISO 45001 LOTO Guardrail"]
    G --> H["GroundedMaintenanceResponse\n(FastAPI JSON)"]
```

---

## Core Enterprise Capabilities

### 1. Deterministic KVKK / GDPR PII Sanitization (`KvkkPiiRedactor`)
Before any maintenance ticket or operator transcript touches the retrieval index or prompt pipeline, sensitive identifiers are deterministically masked and logged as structured `PiiRedactionEvent` audit records:
- **Turkish National ID (`TCKN`):** 11-digit pattern + official algorithmic modulo-10 checksum validator (`is_valid_tckn_checksum`).
- **Turkish IBAN (`TR_IBAN`):** Full 26-character `TRxx...` bank account redaction.
- **Turkish Mobile Phone (`TR_PHONE`), Email (`EMAIL`), and Vehicle License Plates (`TR_PLATE`).**

### 2. Hybrid RRF Retrieval (`HybridRrfRetriever`)
Pure vector search frequently fails on industrial part numbers (`SKU-HD-8841`, `MSD-PLUG-900`) and diagnostic trouble codes (`SRVO-053`, `P0AA6`). This engine combines:
- **Okapi BM25 ($k_1=1.5, b=0.75$):** Exact lexical matching on part numbers, error codes, and equipment categories.
- **Character Trigram Cosine Similarity:** Resilient against typos and morphological variations.
- **Reciprocal Rank Fusion (RRF, $k=60$):** Merges both rankings deterministically without brittle score-calibration weights.

### 3. Document-Level RBAC & ISO 45001 Lockout/Tagout (LOTO) Guardrails (`GroundedMaintenanceResponse`)
- **Clearance Filtering:** High-voltage EV battery (`RESTRICTED_SAFETY_L3`) or robotics servo procedures (`MAINTENANCE_ENGINEER_L2`) are automatically filtered out if queried by an unauthorized clearance tier (`OPERATOR_L1`).
- **Zero-Hallucination Citation Validator:** Pydantic v2 `@model_validator` rejects any non-abstained response that lacks a verbatim `CitationEvidence` quote from an authorized `SOP-*` document.
- **ISO 45001 Safety Interlock:** Any procedure classified as `IMMEDIATE_LINE_STOP` is mathematically forced to set `lockout_tagout_mandatory=True`.

---

## Quick Start & Testing

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run unit & API integration tests
pytest -v

# Start FastAPI server
uvicorn industrial_rag_copilot.api:app --reload --port 8090
```

---

## Repository Structure

```text
├── pyproject.toml
├── src/industrial_rag_copilot/
│   ├── models.py          # Pydantic v2 schemas, RBAC enums, LOTO & citation guardrails
│   ├── pii_redactor.py    # KVKK/GDPR PII redactor & TCKN checksum validator
│   ├── retriever.py       # Okapi BM25 + Dense Trigram Reciprocal Rank Fusion (RRF)
│   ├── service.py         # Orchestration service & abstention handling
│   └── api.py             # FastAPI REST endpoints (/health, /api/v1/copilot/query)
└── tests/
    └── test_industrial_copilot.py
```

---

## License
MIT License. See [LICENSE](LICENSE).
