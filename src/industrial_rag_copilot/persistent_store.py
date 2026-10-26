from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from industrial_rag_copilot.models import (
    GroundedMaintenanceResponse,
    SecurityClearance,
    SopDocumentChunk,
)
from industrial_rag_copilot.retriever import DEFAULT_ENTERPRISE_SOP_CORPUS


class SqliteEnterpriseKnowledgeStore:
    """Persistent SQLite storage for Standard Operating Procedure (SOP) chunks and
    immutable KVKK/RBAC compliance audit logs.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sop_chunks (
                    doc_id TEXT NOT NULL,
                    clause_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    equipment_category TEXT NOT NULL,
                    required_clearance TEXT NOT NULL,
                    lockout_tagout_required INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    part_numbers_json TEXT NOT NULL,
                    PRIMARY KEY (doc_id, clause_id)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compliance_audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    user_clearance TEXT NOT NULL,
                    sanitized_query TEXT NOT NULL,
                    pii_redactions_json TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    loto_mandatory INTEGER NOT NULL,
                    abstained INTEGER NOT NULL,
                    cited_doc_ids_json TEXT NOT NULL
                )
                """
            )

    def seed_default_corpus_if_empty(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) AS cnt FROM sop_chunks")
        count = int(cur.fetchone()["cnt"])
        if count == 0:
            for chunk in DEFAULT_ENTERPRISE_SOP_CORPUS:
                self.upsert_sop_chunk(chunk)
            return len(DEFAULT_ENTERPRISE_SOP_CORPUS)
        return count

    def upsert_sop_chunk(self, chunk: SopDocumentChunk) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO sop_chunks (
                    doc_id, clause_id, title, equipment_category,
                    required_clearance, lockout_tagout_required, content, part_numbers_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.doc_id,
                    chunk.clause_id,
                    chunk.title,
                    chunk.equipment_category,
                    chunk.required_clearance.value,
                    1 if chunk.LockoutTagoutRequired else 0,
                    chunk.content,
                    json.dumps(chunk.part_numbers),
                ),
            )

    def load_all_chunks(self) -> List[SopDocumentChunk]:
        rows = self._conn.execute(
            "SELECT * FROM sop_chunks ORDER BY doc_id ASC, clause_id ASC"
        ).fetchall()
        return [
            SopDocumentChunk(
                doc_id=row["doc_id"],
                clause_id=row["clause_id"],
                title=row["title"],
                equipment_category=row["equipment_category"],
                required_clearance=SecurityClearance(row["required_clearance"]),
                LockoutTagoutRequired=bool(row["lockout_tagout_required"]),
                content=row["content"],
                part_numbers=json.loads(row["part_numbers_json"]),
            )
            for row in rows
        ]

    def record_audit_event(
        self,
        user_clearance: SecurityClearance,
        response: GroundedMaintenanceResponse,
    ) -> int:
        now_utc = datetime.now(timezone.utc).isoformat()
        redactions_payload = [r.model_dump() for r in response.pii_redactions]
        cited_docs = [f"{c.doc_id}#{c.clause_id}" for c in response.citations]
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO compliance_audit_log (
                    timestamp_utc, user_clearance, sanitized_query,
                    pii_redactions_json, urgency, loto_mandatory, abstained, cited_doc_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_utc,
                    user_clearance.value,
                    response.sanitized_query,
                    json.dumps(redactions_payload),
                    response.urgency.value,
                    1 if response.lockout_tagout_mandatory else 0,
                    1 if response.abstained_due_to_insufficient_evidence else 0,
                    json.dumps(cited_docs),
                ),
            )
            return int(cur.lastrowid or 0)

    def list_recent_audit_logs(self, limit: int = 25) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM compliance_audit_log ORDER BY audit_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "audit_id": row["audit_id"],
                "timestamp_utc": row["timestamp_utc"],
                "user_clearance": row["user_clearance"],
                "sanitized_query": row["sanitized_query"],
                "pii_redactions": json.loads(row["pii_redactions_json"]),
                "urgency": row["urgency"],
                "loto_mandatory": bool(row["loto_mandatory"]),
                "abstained": bool(row["abstained"]),
                "cited_doc_ids": json.loads(row["cited_doc_ids_json"]),
            }
            for row in rows
        ]
