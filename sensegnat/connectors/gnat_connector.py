from __future__ import annotations

from dataclasses import asdict

from sensegnat.models.findings import Finding
from sensegnat.models.narratives import Narrative


class GNATConnector:
    """Minimal placeholder for publishing SenseGNAT output into GNAT."""

    def to_record(self, finding: Finding) -> dict:
        payload = asdict(finding)
        payload["product"] = "SenseGNAT"
        payload["record_type"] = "anomaly-finding"
        return payload

    def narrative_to_record(self, narrative: Narrative) -> dict:
        return {
            "product": "SenseGNAT",
            "record_type": "risk-narrative",
            "subject_id": narrative.subject_id,
            "finding_count": narrative.finding_count,
            "finding_types": list(narrative.finding_types),
            "severity": narrative.severity,
            "score": narrative.score,
            "summary": narrative.summary,
        }
