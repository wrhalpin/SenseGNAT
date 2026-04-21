from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent

# Event types that carry a complete network 5-tuple
_SUPPORTED_TYPES = frozenset({"flow", "alert"})

# Normalise Suricata's +0000 offset (no colon) to +00:00 for fromisoformat
_BARE_OFFSET_RE = re.compile(r"([+-])(\d{2})(\d{2})$")


def _parse_timestamp(ts: str) -> datetime:
    ts = _BARE_OFFSET_RE.sub(r"\1\2:\3", ts)
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class SuricataEveAdapter(EventAdapter):
    """Reads NormalizedNetworkEvent from a Suricata EVE JSON file.

    EVE JSON is newline-delimited; each line is one complete JSON record.
    Only 'flow' and 'alert' event types are processed — both carry a full
    network 5-tuple.  All other event types (dns, http, stats, …) are skipped.
    Lines that are blank or contain invalid JSON are skipped silently.

    Field mapping:
      flow_id              → event_id (str; UUID generated if absent)
      timestamp            → seen_at
      src_ip               → source_host
      dest_ip              → destination
      dest_port            → destination_port
      proto                → protocol (lowercased)
      flow.bytes_toserver  → bytes_out (0 when absent)
      flow.bytes_toclient  → bytes_in  (0 when absent)

    source_user is always None — EVE flow/alert records carry no user identity.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        with self._path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = self._parse_record(record)
                if event is not None:
                    yield event

    @staticmethod
    def _parse_record(record: dict) -> NormalizedNetworkEvent | None:
        if record.get("event_type") not in _SUPPORTED_TYPES:
            return None

        src_ip = record.get("src_ip", "")
        dest_ip = record.get("dest_ip", "")
        dest_port = record.get("dest_port")
        proto = record.get("proto", "")
        timestamp = record.get("timestamp", "")

        if not src_ip or not dest_ip or dest_port is None or not timestamp:
            return None

        try:
            seen_at = _parse_timestamp(timestamp)
            destination_port = int(dest_port)
        except (ValueError, OSError):
            return None

        flow = record.get("flow") or {}
        bytes_out = int(flow.get("bytes_toserver") or 0)
        bytes_in = int(flow.get("bytes_toclient") or 0)

        flow_id = record.get("flow_id")
        event_id = str(flow_id) if flow_id is not None else str(uuid4())

        return NormalizedNetworkEvent(
            event_id=event_id,
            seen_at=seen_at,
            source_host=src_ip,
            source_user=None,
            destination=dest_ip,
            destination_port=destination_port,
            protocol=proto.lower(),
            bytes_out=bytes_out,
            bytes_in=bytes_in,
        )
