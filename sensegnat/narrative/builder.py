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

        investigation_id, investigation_link_type = self._pick_investigation(findings)

        return Narrative(
            subject_id=subject_id,
            finding_count=len(findings),
            finding_types=finding_types,
            severity=severity,
            score=score,
            summary=summary,
            investigation_id=investigation_id,
            investigation_link_type=investigation_link_type,
        )

    @staticmethod
    def _pick_investigation(findings: list[Finding]) -> tuple[str | None, str | None]:
        """Return the highest-priority investigation context from a set of findings.

        'confirmed' outranks 'inferred', which outranks 'suggested'. When
        multiple findings share the same rank, the first encountered wins.
        """
        _RANK = {"confirmed": 2, "inferred": 1, "suggested": 0}
        best = max(
            (f for f in findings if f.investigation_id),
            key=lambda f: _RANK.get(f.investigation_link_type or "", 0),
            default=None,
        )
        if best is None:
            return None, None
        return best.investigation_id, best.investigation_link_type
