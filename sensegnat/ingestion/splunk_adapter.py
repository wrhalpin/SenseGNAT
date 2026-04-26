from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import uuid4

from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent

logger = logging.getLogger(__name__)

# splunk-sdk is an optional runtime dependency — same pattern as kafka-python-ng
# in GNATTelemetryAdapter.  The module is always importable; the error surfaces
# only when fetch_events() is called without the SDK installed.
try:
    import splunklib.client as _splunk_client
    import splunklib.results as _splunk_results
except ImportError:
    _splunk_client = None  # type: ignore[assignment]
    _splunk_results = None  # type: ignore[assignment]


def _first_str(*keys_and_record: object) -> str | None:
    """Return the first non-empty string from record[key] for each key."""
    # Called as _first_str(record, "k1", "k2", ...)
    record: dict = keys_and_record[0]  # type: ignore[assignment]
    for key in keys_and_record[1:]:
        v = record.get(key)  # type: ignore[arg-type]
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _int_field(record: dict, *keys: str) -> int:
    for key in keys:
        v = record.get(key)
        if v is not None and str(v).strip():
            try:
                return int(float(str(v)))
            except (ValueError, TypeError):
                pass
    return 0


class SplunkEventAdapter(EventAdapter):
    """Queries Splunk via the REST API and yields NormalizedNetworkEvents.

    The caller supplies a complete SPL query.  The adapter executes it,
    paginates through all results, and maps CIM-normalised fields to
    NormalizedNetworkEvent.  Non-CIM sourcetypes can be handled by
    including ``rename`` or ``eval`` commands in the SPL query.

    Field mapping (primary CIM name → fallbacks):

    =====================  ============================================
    NormalizedNetworkEvent  Splunk fields tried in order
    =====================  ============================================
    source_host             src, src_ip, source_ip, source
    destination             dest, dest_ip, destination_ip, destination
    destination_port        dest_port, destination_port
    protocol                transport, protocol, proto
    bytes_out               bytes_out, bytes_sent, out_bytes
    bytes_in                bytes_in, bytes_received, in_bytes
    seen_at                 _time (Unix epoch float)
    event_id                _cd, auto uuid4()
    source_user             user, src_user
    =====================  ============================================

    Records missing ``src``/``dest``/``dest_port`` after fallback
    resolution are silently skipped.

    Parameters
    ----------
    spl_query:
        A complete SPL search string, e.g.
        ``"search index=network sourcetype=stream:tcp | fields _time, src, dest, dest_port, transport, bytes_in, bytes_out"``.
    host:
        Splunk instance hostname or IP.
    port:
        Splunk management port.  Default: 8089.
    token:
        Bearer token for authentication (recommended).  Takes priority
        over ``username``/``password`` when both are supplied.
    username / password:
        Basic auth credentials.  Used when ``token`` is not provided.
    earliest_time / latest_time:
        Splunk time range modifiers passed to the search job.
        Defaults: ``"-24h"`` / ``"now"``.
    max_results:
        Stop after yielding this many events.  ``None`` means drain all
        results.
    page_size:
        Number of raw records to fetch per pagination request.
        Default: 500.
    """

    def __init__(
        self,
        spl_query: str,
        host: str,
        port: int = 8089,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        earliest_time: str = "-24h",
        latest_time: str = "now",
        max_results: int | None = None,
        page_size: int = 500,
    ) -> None:
        self._spl_query = spl_query
        self._host = host
        self._port = port
        self._token = token
        self._username = username
        self._password = password
        self._earliest_time = earliest_time
        self._latest_time = latest_time
        self._max_results = max_results
        self._page_size = page_size

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        if _splunk_client is None:
            raise ImportError(
                "splunk-sdk is required to use SplunkEventAdapter. "
                "Install it with: pip install sensegnat[splunk]"
            )

        if self._token:
            service = _splunk_client.connect(
                host=self._host,
                port=self._port,
                token=self._token,
            )
        else:
            service = _splunk_client.connect(
                host=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
            )

        job = service.jobs.create(
            self._spl_query,
            earliest_time=self._earliest_time,
            latest_time=self._latest_time,
            exec_mode="blocking",
        )

        emitted = 0
        offset = 0
        try:
            while True:
                fetch_count = self._page_size
                if self._max_results is not None:
                    remaining = self._max_results - emitted
                    if remaining <= 0:
                        break
                    fetch_count = min(self._page_size, remaining)

                response = job.results(
                    output_mode="json",
                    count=fetch_count,
                    offset=offset,
                )

                raw_count = 0
                done = False
                for result in _splunk_results.JSONResultsReader(response):
                    if isinstance(result, _splunk_results.Message):
                        logger.debug(
                            "Splunk [%s]: %s", result.type, result.message
                        )
                        continue
                    if not isinstance(result, dict):
                        continue
                    raw_count += 1
                    event = self._parse_record(result)
                    if event is not None:
                        yield event
                        emitted += 1
                        if self._max_results is not None and emitted >= self._max_results:
                            done = True
                            break

                if done or raw_count == 0:
                    break
                offset += raw_count
        finally:
            logger.info(
                "SplunkEventAdapter: yielded %d events from %s",
                emitted,
                self._host,
            )

    @staticmethod
    def _parse_record(record: dict) -> NormalizedNetworkEvent | None:
        src = _first_str(record, "src", "src_ip", "source_ip", "source")
        dest = _first_str(record, "dest", "dest_ip", "destination_ip", "destination")
        dest_port_raw = _first_str(record, "dest_port", "destination_port")

        if not src or not dest or dest_port_raw is None:
            return None

        try:
            destination_port = int(float(dest_port_raw))
        except (ValueError, TypeError):
            return None

        proto_raw = _first_str(record, "transport", "protocol", "proto") or ""
        protocol = proto_raw.lower()

        bytes_out = _int_field(record, "bytes_out", "bytes_sent", "out_bytes")
        bytes_in = _int_field(record, "bytes_in", "bytes_received", "in_bytes")

        time_raw = record.get("_time")
        if time_raw is not None and str(time_raw).strip():
            try:
                seen_at = datetime.fromtimestamp(float(time_raw), tz=timezone.utc)
            except (ValueError, OSError):
                seen_at = datetime.now(timezone.utc)
        else:
            seen_at = datetime.now(timezone.utc)

        event_id = str(record.get("_cd") or uuid4())

        user_raw = _first_str(record, "user", "src_user")
        source_user: str | None = user_raw if user_raw else None

        return NormalizedNetworkEvent(
            event_id=event_id,
            seen_at=seen_at,
            source_host=src,
            source_user=source_user,
            destination=dest,
            destination_port=destination_port,
            protocol=protocol,
            bytes_out=bytes_out,
            bytes_in=bytes_in,
        )
