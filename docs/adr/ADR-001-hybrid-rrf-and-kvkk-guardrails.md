# ADR-001: Hybrid BM25 + Trigram Reciprocal Rank Fusion (RRF) and Pre-Indexing KVKK Redaction

- **Status:** Accepted
- **Date:** 2026-10-26

## Context
Industrial maintenance tickets and factory operator reports frequently contain both exact alphanumeric equipment SKUs / fault codes (`SRVO-053`, `P0AA6`, `SKU-HD-8841`) and unstructured personal data (operator Turkish National ID `TCKN`, phone numbers, license plates, corporate emails). Pure dense vector embeddings struggle with exact part-number recall, while unredacted transcripts violate Turkish KVKK and EU GDPR data minimization principles.

## Decision
1. **Deterministic Pre-Retrieval KVKK Sanitization (`KvkkPiiRedactor`):** Strip and log `TCKN`, `TR_IBAN`, `TR_PHONE`, `EMAIL`, and `TR_PLATE` prior to retrieval or prompt assembly.
2. **Reciprocal Rank Fusion (`HybridRrfRetriever`):** Combine Okapi BM25 lexical scoring with character trigram cosine similarity via RRF ($k=60$) after filtering the corpus by the caller's `SecurityClearance` tier.
3. **Pydantic v2 Output Guardrail (`GroundedMaintenanceResponse`):** Reject any non-abstained response lacking verbatim `SOP-*` citations or violating ISO 45001 Lockout/Tagout (`lockout_tagout_mandatory=True` on `IMMEDIATE_LINE_STOP`).

## Consequences
- **Positive:** 100% recall on exact part numbers and fault codes while maintaining typo resilience and strict KVKK/RBAC compliance.
- **Negative:** Requires curated `SOP-*` metadata (`required_clearance`, `LockoutTagoutRequired`) during document ingestion.
