from __future__ import annotations

from dataclasses import asdict

from sensegnat.models.findings import Finding


class GNATConnector:
    """Minimal placeholder for publishing SenseGNAT output into GNAT."""

    def to_record(self, finding: Finding) -> dict:
        payload = asdict(finding)
        payload["product"] = "SenseGNAT"
        payload["record_type"] = "anomaly-finding"
        return payload
