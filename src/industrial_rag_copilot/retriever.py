from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple
from industrial_rag_copilot.models import (
    CitationEvidence,
    MaintenanceUrgency,
    SecurityClearance,
    SopDocumentChunk,
)


_CLEARANCE_RANK: Dict[SecurityClearance, int] = {
    SecurityClearance.PUBLIC: 0,
    SecurityClearance.OPERATOR_L1: 1,
    SecurityClearance.MAINTENANCE_ENGINEER_L2: 2,
    SecurityClearance.RESTRICTED_SAFETY_L3: 3,
}


def _tokenize(text: str) -> List[str]:
    return [tok for tok in re.findall(r"[a-z0-9-]+", text.lower()) if len(tok) >= 2]


def _char_trigram_vector(text: str) -> Counter[str]:
    cleaned = re.sub(r"\s+", " ", text.lower()).strip()
    if len(cleaned) < 3:
        return Counter({cleaned: 1})
    return Counter(cleaned[i : i + 3] for i in range(len(cleaned) - 2))


def _cosine_similarity(vec_a: Counter[str], vec_b: Counter[str]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    intersection = set(vec_a.keys()) & set(vec_b.keys())
    numerator = sum(vec_a[k] * vec_b[k] for k in intersection)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return numerator / (norm_a * norm_b)


class HybridRrfRetriever:
    """Enterprise Hybrid Retriever combining Okapi BM25 lexical matching (for exact part
    numbers, SKU codes, and SAE/ISO error codes) with character-n-gram dense cosine similarity,
    merged via Reciprocal Rank Fusion (RRF) and RBAC security clearance filtering.
    """

    def __init__(self, chunks: List[SopDocumentChunk], k1: float = 1.5, b: float = 0.75, rrf_k: int = 60) -> None:
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self.rrf_k = rrf_k

        self._doc_tokens: List[List[str]] = [
            _tokenize(f"{c.title} {c.equipment_category} {' '.join(c.part_numbers)} {c.content}")
            for c in self.chunks
        ]
        self._doc_freqs: Counter[str] = Counter()
        for tokens in self._doc_tokens:
            for unique_token in set(tokens):
                self._doc_freqs[unique_token] += 1

        total_len = sum(len(t) for t in self._doc_tokens)
        self._avgdl = total_len / max(1, len(self._doc_tokens))
        self._trigram_vecs: List[Counter[str]] = [
            _char_trigram_vector(f"{c.title} {c.content}") for c in self.chunks
        ]

    def _bm25_score(self, query_tokens: List[str], doc_idx: int) -> float:
        doc_tokens = self._doc_tokens[doc_idx]
        if not doc_tokens or not query_tokens:
            return 0.0
        tf_counter = Counter(doc_tokens)
        doc_len = len(doc_tokens)
        n_docs = len(self.chunks)
        score = 0.0
        for q in query_tokens:
            df = self._doc_freqs.get(q, 0)
            if df == 0:
                continue
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            tf = tf_counter[q]
            denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self._avgdl))
            score += idf * ((tf * (self.k1 + 1.0)) / denom)
        return score

    def search(
        self,
        query: str,
        user_clearance: SecurityClearance,
        top_k: int = 3,
    ) -> List[Tuple[SopDocumentChunk, float]]:
        max_allowed_rank = _CLEARANCE_RANK[user_clearance]
        eligible_indices = [
            idx
            for idx, chunk in enumerate(self.chunks)
            if _CLEARANCE_RANK[chunk.required_clearance] <= max_allowed_rank
        ]
        if not eligible_indices:
            return []

        q_tokens = _tokenize(query)
        q_trigram = _char_trigram_vector(query)

        bm25_scores = {idx: self._bm25_score(q_tokens, idx) for idx in eligible_indices}
        dense_scores = {idx: _cosine_similarity(q_trigram, self._trigram_vecs[idx]) for idx in eligible_indices}

        bm25_ranked = sorted(eligible_indices, key=lambda i: bm25_scores[i], reverse=True)
        dense_ranked = sorted(eligible_indices, key=lambda i: dense_scores[i], reverse=True)

        bm25_rank_pos = {idx: rank + 1 for rank, idx in enumerate(bm25_ranked)}
        dense_rank_pos = {idx: rank + 1 for rank, idx in enumerate(dense_ranked)}

        rrf_results: List[Tuple[SopDocumentChunk, float]] = []
        for idx in eligible_indices:
            if bm25_scores[idx] == 0.0 and dense_scores[idx] < 0.08:
                continue
            rrf_score = (1.0 / (self.rrf_k + bm25_rank_pos[idx])) + (1.0 / (self.rrf_k + dense_rank_pos[idx]))
            rrf_results.append((self.chunks[idx], round(rrf_score, 6)))

        rrf_results.sort(key=lambda pair: pair[1], reverse=True)
        return rrf_results[:top_k]


DEFAULT_ENTERPRISE_SOP_CORPUS: List[SopDocumentChunk] = [
    SopDocumentChunk(
        doc_id="SOP-ROBOTICS-001",
        clause_id="4.2.1",
        title="6-Axis Spot Welding Robot Servo Torque Fault & Encoder Calibration",
        equipment_category="Body-in-White (BIW) Welding Robotics",
        required_clearance=SecurityClearance.MAINTENANCE_ENGINEER_L2,
        LockoutTagoutRequired=True,
        content=(
            "When Axis-3 servo over-torque fault SRVO-053 occurs on the BIW spot welding cell, "
            "immediately engage emergency stop and apply Lockout/Tagout (LOTO) padlock on the "
            "400V main cabinet breaker before inspecting harmonic drive reducer part SKU-HD-8841."
        ),
        part_numbers=["SKU-HD-8841", "ENC-AX3-200"],
    ),
    SopDocumentChunk(
        doc_id="SOP-BATTERY-HV-002",
        clause_id="7.1.3",
        title="High-Voltage EV Battery Pack Isolation Fault P0AA6 Containment Protocol",
        equipment_category="e-Mobility HV Battery Assembly",
        required_clearance=SecurityClearance.RESTRICTED_SAFETY_L3,
        LockoutTagoutRequired=True,
        content=(
            "Upon detection of isolation fault P0AA6 (<100 Ohm/V), isolate the pack on the thermal "
            "quarantine bay, wear Class-0 1000V insulated gloves, pull Manual Service Disconnect "
            "(MSD-PLUG-900), and verify zero potential before replacing HV contactor SKU-HVC-450."
        ),
        part_numbers=["MSD-PLUG-900", "SKU-HVC-450"],
    ),
    SopDocumentChunk(
        doc_id="SOP-PAINT-HVAC-003",
        clause_id="2.4.0",
        title="Paint Booth Airflow Differential Pressure Filter Replacement",
        equipment_category="Paint Shop HVAC & Filtration",
        required_clearance=SecurityClearance.OPERATOR_L1,
        LockoutTagoutRequired=False,
        content=(
            "If booth differential pressure exceeds 240 Pa during primer application, schedule "
            "filter cassette replacement using HEPA filter unit SKU-FLT-204 within 48 hours."
        ),
        part_numbers=["SKU-FLT-204"],
    ),
]
