from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent


class CsvEventAdapter(EventAdapter):
    """Reads NormalizedNetworkEvent records from a CSV file.

    Required columns: seen_at, source_host, destination, destination_port, protocol
    Optional columns: event_id, source_user, bytes_out, bytes_in

    seen_at accepts ISO 8601 strings or Unix epoch floats.
    Empty source_user is treated as None (host-only identity).
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        with self._path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                yield self._parse_row(row)

    @staticmethod
    def _parse_row(row: dict[str, str]) -> NormalizedNetworkEvent:
        seen_at_raw = row["seen_at"].strip()
        try:
            seen_at = datetime.fromisoformat(seen_at_raw).replace(tzinfo=timezone.utc)
        except ValueError:
            seen_at = datetime.fromtimestamp(float(seen_at_raw), tz=timezone.utc)

        source_user = row.get("source_user", "").strip() or None

        return NormalizedNetworkEvent(
            event_id=row.get("event_id", "").strip() or str(uuid4()),
            seen_at=seen_at,
            source_host=row["source_host"].strip(),
            source_user=source_user,
            destination=row["destination"].strip(),
            destination_port=int(row["destination_port"]),
            protocol=row["protocol"].strip().lower(),
            bytes_out=int(row.get("bytes_out") or 0),
            bytes_in=int(row.get("bytes_in") or 0),
        )
