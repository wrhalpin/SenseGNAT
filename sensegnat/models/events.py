from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NormalizedNetworkEvent:
    event_id: str
    seen_at: datetime
    source_host: str
    source_user: str | None
    destination: str
    destination_port: int
    protocol: str
    bytes_out: int = 0
    bytes_in: int = 0
    # Set by GNATTelemetryAdapter when the Kafka record carries _gnat_investigation_hint
    investigation_hint: str | None = None
