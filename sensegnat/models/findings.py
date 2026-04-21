from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Finding:
    finding_id: str
    finding_type: str
    seen_at: datetime
    subject_id: str
    severity: str
    score: float
    summary: str
    evidence: dict[str, str]
