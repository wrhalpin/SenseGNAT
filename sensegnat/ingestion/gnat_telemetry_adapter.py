from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import uuid4

from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent

logger = logging.getLogger(__name__)

# Sensor types that carry a complete network 5-tuple.  dns_log and generic
# records do not have both src and dst IPs so they are skipped.
_FLOW_TYPES = frozenset({"netflow", "ids_alert", "honeypot"})

# kafka-python-ng is an optional runtime dependency.  Import it at module
# level so tests can patch the name; set to None when the package is absent
# so the module is always importable.
try:
    from kafka import KafkaConsumer
except ImportError:
    KafkaConsumer = None  # type: ignore[assignment,misc]


def _parse_timestamp(raw: object) -> datetime:
    if isinstance(raw, (int, float)):
        # Kafka timestamps are epoch milliseconds; plain floats are seconds
        ts = raw / 1000.0 if raw > 1e10 else float(raw)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(raw, str) and raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class GNATTelemetryAdapter(EventAdapter):
    """Consumes live sensor telemetry from the Kafka topic shared with GNAT.

    GNAT's ingest pipeline reads raw sensor records from Kafka, normalises
    them into SensorEvent objects, and converts them to STIX Indicators.
    This adapter taps the same Kafka topic *before* that pipeline, giving
    SenseGNAT access to the full network five-tuple needed for behavioural
    profiling.

    Supported sensor_type values: ``netflow``, ``ids_alert``, ``honeypot``.
    All other types (``dns_log``, ``generic``) are skipped because they do
    not carry both source and destination IPs.

    Field mapping from raw Kafka record to NormalizedNetworkEvent:

    ========================  =============================================
    Kafka field(s)            NormalizedNetworkEvent field
    ========================  =============================================
    src_ip / IPV4_SRC_ADDR    source_host
    dst_ip / IPV4_DST_ADDR    destination
    dst_port / L4_DST_PORT    destination_port (0 when absent)
    protocol                  protocol (lowercased)
    timestamp / _kafka_ts     seen_at  (epoch-ms or ISO 8601)
    bytes_out / IN_BYTES /    bytes_out (0 when absent)
      orig_bytes
    bytes_in / OUT_BYTES /    bytes_in  (0 when absent)
      resp_bytes
    tags[0]                   source_user (None when absent)
    flow_id / uid / uuid4()   event_id
    ========================  =============================================

    Parameters
    ----------
    topic : str
        Kafka topic name.  Default: ``"gnat.telemetry"``.
    brokers : list[str]
        Kafka broker addresses.  Default: ``["localhost:9092"]``.
    group_id : str
        Consumer group ID for offset management.  Default: ``"sensegnat"``.
    max_messages : int | None
        Stop after this many events.  ``None`` means drain until the poll
        timeout fires.
    poll_timeout_ms : int
        Milliseconds to wait for new messages before considering the topic
        exhausted.  Default: 5 000.
    sensor_types : frozenset[str] | None
        Override the default set of accepted sensor types.
    """

    def __init__(
        self,
        topic: str = "gnat.telemetry",
        brokers: list[str] | None = None,
        group_id: str = "sensegnat",
        max_messages: int | None = None,
        poll_timeout_ms: int = 5_000,
        sensor_types: frozenset[str] | None = None,
    ) -> None:
        self._topic = topic
        self._brokers = brokers or ["localhost:9092"]
        self._group_id = group_id
        self._max_messages = max_messages
        self._poll_timeout_ms = poll_timeout_ms
        self._sensor_types = sensor_types if sensor_types is not None else _FLOW_TYPES

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        if KafkaConsumer is None:
            raise ImportError(
                "kafka-python-ng is required to use GNATTelemetryAdapter. "
                "Install it with: pip install kafka-python-ng"
            )

        consumer = KafkaConsumer(
            self._topic,
            bootstrap_servers=self._brokers,
            group_id=self._group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            consumer_timeout_ms=self._poll_timeout_ms,
        )

        count = 0
        try:
            for message in consumer:
                record: dict = message.value
                record.setdefault("_kafka_topic", message.topic)
                record.setdefault("_kafka_partition", message.partition)
                record.setdefault("_kafka_offset", message.offset)

                event = self._parse_record(record, self._sensor_types)
                if event is not None:
                    yield event
                    count += 1
                    if self._max_messages is not None and count >= self._max_messages:
                        break
        finally:
            consumer.close()
            logger.info(
                "GNATTelemetryAdapter: consumed %d events from %s",
                count,
                self._topic,
            )

    @staticmethod
    def _parse_record(
        record: dict,
        sensor_types: frozenset[str] = _FLOW_TYPES,
    ) -> NormalizedNetworkEvent | None:
        sensor_type = record.get("sensor_type", "generic")
        if sensor_type not in sensor_types:
            return None

        # Accept both standard SensorEvent names and NetFlow v9 field names
        src_ip = record.get("src_ip") or record.get("IPV4_SRC_ADDR") or ""
        dst_ip = record.get("dst_ip") or record.get("IPV4_DST_ADDR") or ""
        if not src_ip or not dst_ip:
            return None

        dst_port = int(
            record.get("dst_port")
            or record.get("L4_DST_PORT")
            or record.get("dest_port")
            or 0
        )
        protocol = (record.get("protocol") or "").lower()

        raw_ts = (
            record.get("timestamp")
            or record.get("_kafka_timestamp")
            or ""
        )
        seen_at = _parse_timestamp(raw_ts)

        bytes_out = int(
            record.get("bytes_out")
            or record.get("IN_BYTES")
            or record.get("orig_bytes")
            or 0
        )
        bytes_in = int(
            record.get("bytes_in")
            or record.get("OUT_BYTES")
            or record.get("resp_bytes")
            or 0
        )

        # tags[0] carries the subject identity when the sensor is identity-aware
        tags: list = record.get("tags") or []
        source_user: str | None = str(tags[0]) if tags else None

        event_id = str(record.get("flow_id") or record.get("uid") or uuid4())
        investigation_hint = record.get("_gnat_investigation_hint") or None

        return NormalizedNetworkEvent(
            event_id=event_id,
            seen_at=seen_at,
            source_host=src_ip,
            source_user=source_user,
            destination=dst_ip,
            destination_port=dst_port,
            protocol=protocol,
            bytes_out=bytes_out,
            bytes_in=bytes_in,
            investigation_hint=investigation_hint,
        )
