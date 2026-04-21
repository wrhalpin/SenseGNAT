from __future__ import annotations

from collections import Counter

from sensegnat.models.findings import Finding
from sensegnat.models.narratives import Narrative

_SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class NarrativeBuilder:
    """Rolls a set of per-subject findings into a single structured narrative."""

    def build(self, subject_id: str, findings: list[Finding]) -> Narrative | None:
        if not findings:
            return None

        type_counts: Counter[str] = Counter(f.finding_type for f in findings)
        finding_types = tuple(t for t, _ in type_counts.most_common())
        severity = max(findings, key=lambda f: _SEVERITY_RANK.get(f.severity, 0)).severity
        score = max(f.score for f in findings)

        type_summary = ", ".join(
            f"{t} ×{c}" if c > 1 else t for t, c in type_counts.most_common()
        )
        summary = (
            f"{subject_id}: {len(findings)} finding(s) — {type_summary}. "
            f"Severity: {severity}, peak score: {score:.2f}."
        )

        return Narrative(
            subject_id=subject_id,
            finding_count=len(findings),
            finding_types=finding_types,
            severity=severity,
            score=score,
            summary=summary,
        )
