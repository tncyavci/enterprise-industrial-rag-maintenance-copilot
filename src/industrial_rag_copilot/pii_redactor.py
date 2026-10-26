from __future__ import annotations

import re
from typing import List, Tuple
from industrial_rag_copilot.models import PiiRedactionEvent


class KvkkPiiRedactor:
    """Deterministic KVKK / GDPR PII and corporate secret redaction engine.

    Scans incoming maintenance tickets, operator transcripts, and OCR outputs before
    indexing or LLM prompt construction, replacing sensitive Turkish & international
    identifiers with deterministic tokens.
    """

    _PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
        # Turkish TR IBAN (TR + 2 check digits + 22 alphanumeric/digits, optional spaces)
        ("TR_IBAN", re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.IGNORECASE), "[REDACTED_TR_IBAN]"),
        # Turkish National ID (TCKN - 11 digits starting with non-zero)
        ("TCKN", re.compile(r"\b[1-9]\d{10}\b"), "[REDACTED_TCKN]"),
        # Turkish Mobile Phone (+90 5xx xxx xx xx or 05xx xxx xx xx)
        ("TR_PHONE", re.compile(r"(?:\+90|0)\s?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"), "[REDACTED_TR_PHONE]"),
        # Email Address
        ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
        # Turkish Vehicle License Plate (e.g., 34 ABC 123 or 16 TFS 45)
        ("TR_PLATE", re.compile(r"\b(?:0[1-9]|[1-7]\d|8[01])\s+[A-Z]{1,3}\s+\d{2,4}\b"), "[REDACTED_TR_PLATE]"),
    ]

    @staticmethod
    def is_valid_tckn_checksum(candidate: str) -> bool:
        """Validates the official 11-digit Turkish National ID (TCKN) algorithmic checksum."""
        if len(candidate) != 11 or not candidate.isdigit() or candidate[0] == "0":
            return False
        digits = [int(ch) for ch in candidate]
        odd_sum = digits[0] + digits[2] + digits[4] + digits[6] + digits[8]
        even_sum = digits[1] + digits[3] + digits[5] + digits[7]
        tenth = ((odd_sum * 7) - even_sum) % 10
        eleventh = sum(digits[:10]) % 10
        return digits[9] == tenth and digits[10] == eleventh

    def sanitize(self, raw_text: str) -> Tuple[str, List[PiiRedactionEvent]]:
        sanitized = raw_text
        events: List[PiiRedactionEvent] = []

        for entity_type, pattern, replacement in self._PATTERNS:
            matches = list(pattern.finditer(sanitized))
            if matches:
                sanitized = pattern.sub(replacement, sanitized)
                events.append(
                    PiiRedactionEvent(
                        entity_type=entity_type,
                        redacted_count=len(matches),
                    )
                )

        return sanitized, events
