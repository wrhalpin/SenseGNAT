from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent


class SampleEventAdapter(EventAdapter):
    """Simple adapter used to exercise the Phase A pipeline."""

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        return [
            NormalizedNetworkEvent(
                event_id="evt-001",
                seen_at=datetime.now(timezone.utc),
                source_host="host-1",
                source_user="alice",
                destination="198.51.100.44",
                destination_port=443,
                protocol="tcp",
                bytes_out=1048576,
                bytes_in=2201,
            )
        ]
