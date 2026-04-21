from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent

_UNSET = {"-", "(empty)"}


def _int_or_zero(value: str) -> int:
    if value in _UNSET:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


class ZeekConnLogAdapter(EventAdapter):
    """Reads NormalizedNetworkEvent records from a Zeek conn.log file.

    Zeek conn.log is tab-separated with # comment/header lines.  The
    #fields line defines the column order; all other # lines are skipped.
    Unset values ('-') and empty values ('(empty)') are treated as absent.

    Field mapping:
      uid        → event_id
      ts         → seen_at  (Unix epoch float)
      id.orig_h  → source_host
      id.resp_h  → destination
      id.resp_p  → destination_port
      proto      → protocol (lowercased)
      orig_bytes → bytes_out (0 when unset)
      resp_bytes → bytes_in  (0 when unset)

    source_user is always None — conn.log carries no user identity.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        fields: list[str] = []
        with self._path.open() as fh:
            for raw_line in fh:
                line = raw_line.rstrip("\n")
                if line.startswith("#fields"):
                    fields = line.split("\t")[1:]
                    continue
                if line.startswith("#") or not line.strip():
                    continue
                if not fields:
                    continue
                row = dict(zip(fields, line.split("\t")))
                event = self._parse_row(row)
                if event is not None:
                    yield event

    @staticmethod
    def _parse_row(row: dict[str, str]) -> NormalizedNetworkEvent | None:
        ts_raw = row.get("ts", "")
        resp_h = row.get("id.resp_h", "")
        resp_p = row.get("id.resp_p", "")
        proto = row.get("proto", "")

        if ts_raw in _UNSET or resp_h in _UNSET or resp_p in _UNSET:
            return None

        try:
            seen_at = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
            destination_port = int(resp_p)
        except (ValueError, OSError):
            return None

        return NormalizedNetworkEvent(
            event_id=row.get("uid", "") or str(uuid4()),
            seen_at=seen_at,
            source_host=row.get("id.orig_h", "") or "unknown",
            source_user=None,
            destination=resp_h,
            destination_port=destination_port,
            protocol=proto.lower() if proto not in _UNSET else "unknown",
            bytes_out=_int_or_zero(row.get("orig_bytes", "-")),
            bytes_in=_int_or_zero(row.get("resp_bytes", "-")),
        )
