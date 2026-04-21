from __future__ import annotations

from sensegnat.common.serialization import to_dict
from sensegnat.models.findings import Finding
from sensegnat.models.narratives import Narrative


class GNATConnector:
    """Minimal placeholder for publishing SenseGNAT output into GNAT."""

    def to_record(self, finding: Finding) -> dict:
        payload = to_dict(finding)
        payload["product"] = "SenseGNAT"
        payload["record_type"] = "anomaly-finding"
        return payload

    def narrative_to_record(self, narrative: Narrative) -> dict:
        payload = to_dict(narrative)
        payload["product"] = "SenseGNAT"
        payload["record_type"] = "risk-narrative"
        return payload
