from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Narrative:
    subject_id: str
    finding_count: int
    finding_types: tuple[str, ...]  # ordered by frequency, most common first
    severity: str                   # highest severity rolled up across all findings
    score: float                    # peak score across all findings
    summary: str
    investigation_id: str | None = None
    investigation_link_type: str | None = None
