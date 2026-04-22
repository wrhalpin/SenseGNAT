from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import sensegnat.ingestion.gnat_telemetry_adapter as _mod
from sensegnat.ingestion.gnat_telemetry_adapter import GNATTelemetryAdapter


# ── helpers ────────────────────────────────────────────────────────────────────

def _msg(value: dict, topic: str = "gnat.telemetry", partition: int = 0, offset: int = 0):
    m = MagicMock()
    m.value = value
    m.topic = topic
    m.partition = partition
    m.offset = offset
    return m


def _consumer(records: list[dict]) -> MagicMock:
    """Minimal KafkaConsumer mock that iterates over *records* once."""
    mock = MagicMock()
    mock.__iter__ = MagicMock(return_value=iter([_msg(r) for r in records]))
    mock.close = MagicMock()
    return mock


def _fetch(records: list[dict], **kw) -> list:
    with patch.object(_mod, "KafkaConsumer", return_value=_consumer(records)):
        return list(GNATTelemetryAdapter(**kw).fetch_events())


_NETFLOW = {
    "sensor_type": "netflow",
    "sensor_id": "sensor-01",
    "src_ip": "192.168.1.10",
    "src_port": 54321,
    "dst_ip": "203.0.113.10",
    "dst_port": 443,
    "protocol": "tcp",
    "bytes_out": 1024,
    "bytes_in": 512,
    "timestamp": "2024-01-15T10:00:00+00:00",
}


# ── field mapping ──────────────────────────────────────────────────────────────

class TestFieldMapping:
    def test_source_host(self) -> None:
        assert _fetch([_NETFLOW])[0].source_host == "192.168.1.10"

    def test_destination(self) -> None:
        assert _fetch([_NETFLOW])[0].destination == "203.0.113.10"

    def test_destination_port(self) -> None:
        assert _fetch([_NETFLOW])[0].destination_port == 443

    def test_protocol_lowercased(self) -> None:
        r = {**_NETFLOW, "protocol": "UDP"}
        assert _fetch([r])[0].protocol == "udp"

    def test_protocol_already_lowercase(self) -> None:
        assert _fetch([_NETFLOW])[0].protocol == "tcp"

    def test_bytes_out(self) -> None:
        assert _fetch([_NETFLOW])[0].bytes_out == 1024

    def test_bytes_in(self) -> None:
        assert _fetch([_NETFLOW])[0].bytes_in == 512

    def test_bytes_default_to_zero_when_absent(self) -> None:
        r = {k: v for k, v in _NETFLOW.items() if k not in ("bytes_out", "bytes_in")}
        e = _fetch([r])[0]
        assert e.bytes_out == 0
        assert e.bytes_in == 0

    def test_source_user_from_tags(self) -> None:
        r = {**_NETFLOW, "tags": ["alice"]}
        assert _fetch([r])[0].source_user == "alice"

    def test_source_user_none_when_no_tags(self) -> None:
        assert _fetch([_NETFLOW])[0].source_user is None

    def test_source_user_none_when_tags_empty(self) -> None:
        r = {**_NETFLOW, "tags": []}
        assert _fetch([r])[0].source_user is None

    def test_event_id_from_flow_id(self) -> None:
        r = {**_NETFLOW, "flow_id": "abc-123"}
        assert _fetch([r])[0].event_id == "abc-123"

    def test_event_id_from_uid(self) -> None:
        r = {**_NETFLOW, "uid": "CxAABB1"}
        assert _fetch([r])[0].event_id == "CxAABB1"

    def test_event_id_generated_when_absent(self) -> None:
        e = _fetch([_NETFLOW])[0]
        assert e.event_id  # non-empty UUID


# ── timestamp parsing ──────────────────────────────────────────────────────────

class TestTimestampParsing:
    _TS = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_iso_with_offset(self) -> None:
        assert _fetch([_NETFLOW])[0].seen_at == self._TS

    def test_iso_with_z_suffix(self) -> None:
        r = {**_NETFLOW, "timestamp": "2024-01-15T10:00:00Z"}
        assert _fetch([r])[0].seen_at == self._TS

    def test_epoch_milliseconds(self) -> None:
        r = {**_NETFLOW, "timestamp": 1705312800000}
        assert _fetch([r])[0].seen_at == self._TS

    def test_epoch_seconds_float(self) -> None:
        r = {**_NETFLOW, "timestamp": 1705312800.0}
        assert _fetch([r])[0].seen_at == self._TS

    def test_missing_timestamp_returns_aware_datetime(self) -> None:
        r = {k: v for k, v in _NETFLOW.items() if k != "timestamp"}
        e = _fetch([r])[0]
        assert e.seen_at.tzinfo is not None


# ── sensor type filtering ──────────────────────────────────────────────────────

class TestSensorTypeFiltering:
    def test_netflow_accepted(self) -> None:
        assert len(_fetch([_NETFLOW])) == 1

    def test_ids_alert_accepted(self) -> None:
        r = {**_NETFLOW, "sensor_type": "ids_alert"}
        assert len(_fetch([r])) == 1

    def test_honeypot_accepted(self) -> None:
        r = {**_NETFLOW, "sensor_type": "honeypot"}
        assert len(_fetch([r])) == 1

    def test_dns_log_skipped(self) -> None:
        r = {**_NETFLOW, "sensor_type": "dns_log"}
        assert _fetch([r]) == []

    def test_generic_skipped(self) -> None:
        r = {**_NETFLOW, "sensor_type": "generic"}
        assert _fetch([r]) == []

    def test_custom_sensor_types_override_default(self) -> None:
        r = {**_NETFLOW, "sensor_type": "dns_log"}
        events = _fetch([r], sensor_types=frozenset({"dns_log"}))
        assert len(events) == 1


# ── skip conditions ────────────────────────────────────────────────────────────

class TestSkipConditions:
    def test_missing_src_ip_skipped(self) -> None:
        r = {k: v for k, v in _NETFLOW.items() if k != "src_ip"}
        assert _fetch([r]) == []

    def test_missing_dst_ip_skipped(self) -> None:
        r = {k: v for k, v in _NETFLOW.items() if k != "dst_ip"}
        assert _fetch([r]) == []

    def test_empty_src_ip_skipped(self) -> None:
        r = {**_NETFLOW, "src_ip": ""}
        assert _fetch([r]) == []

    def test_empty_dst_ip_skipped(self) -> None:
        r = {**_NETFLOW, "dst_ip": ""}
        assert _fetch([r]) == []


# ── NetFlow v9 alternate field names ──────────────────────────────────────────

class TestNetFlowV9FieldNames:
    _V9 = {
        "sensor_type": "netflow",
        "IPV4_SRC_ADDR": "10.0.0.1",
        "IPV4_DST_ADDR": "203.0.113.10",
        "L4_DST_PORT": 443,
        "L4_SRC_PORT": 12345,
        "IN_BYTES": 2048,
        "OUT_BYTES": 256,
        "timestamp": "2024-01-15T10:00:00+00:00",
    }

    def test_src_ip_alternate_name(self) -> None:
        assert _fetch([self._V9])[0].source_host == "10.0.0.1"

    def test_dst_ip_alternate_name(self) -> None:
        assert _fetch([self._V9])[0].destination == "203.0.113.10"

    def test_dst_port_alternate_name(self) -> None:
        assert _fetch([self._V9])[0].destination_port == 443

    def test_bytes_out_alternate_name(self) -> None:
        assert _fetch([self._V9])[0].bytes_out == 2048

    def test_bytes_in_alternate_name(self) -> None:
        assert _fetch([self._V9])[0].bytes_in == 256


# ── max_messages ───────────────────────────────────────────────────────────────

class TestMaxMessages:
    def test_max_messages_limits_output(self) -> None:
        records = [_NETFLOW] * 10
        assert len(_fetch(records, max_messages=3)) == 3

    def test_max_messages_none_returns_all(self) -> None:
        records = [_NETFLOW] * 5
        assert len(_fetch(records, max_messages=None)) == 5

    def test_empty_topic_yields_nothing(self) -> None:
        assert _fetch([]) == []


# ── multiple records ───────────────────────────────────────────────────────────

class TestMultipleRecords:
    def test_all_parsed(self) -> None:
        records = [
            {**_NETFLOW, "dst_ip": "10.0.0.1", "dst_port": 443},
            {**_NETFLOW, "dst_ip": "10.0.0.2", "dst_port": 80, "sensor_type": "ids_alert"},
            {**_NETFLOW, "dst_ip": "10.0.0.3", "dst_port": 22},
        ]
        events = _fetch(records)
        assert len(events) == 3
        assert {e.destination for e in events} == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}

    def test_mixed_accepted_and_skipped(self) -> None:
        records = [
            _NETFLOW,
            {**_NETFLOW, "sensor_type": "dns_log"},
            {**_NETFLOW, "dst_ip": "10.0.0.2"},
        ]
        assert len(_fetch(records)) == 2


# ── kafka unavailable ──────────────────────────────────────────────────────────

class TestKafkaUnavailable:
    def test_raises_import_error_when_kafka_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_mod, "KafkaConsumer", None)
        with pytest.raises(ImportError, match="kafka-python-ng"):
            list(GNATTelemetryAdapter().fetch_events())


# ── consumer lifecycle ─────────────────────────────────────────────────────────

class TestConsumerLifecycle:
    def test_consumer_closed_after_iteration(self) -> None:
        mock = _consumer([_NETFLOW])
        with patch.object(_mod, "KafkaConsumer", return_value=mock):
            list(GNATTelemetryAdapter().fetch_events())
        mock.close.assert_called_once()

    def test_consumer_closed_on_max_messages(self) -> None:
        mock = _consumer([_NETFLOW] * 5)
        with patch.object(_mod, "KafkaConsumer", return_value=mock):
            list(GNATTelemetryAdapter(max_messages=2).fetch_events())
        mock.close.assert_called_once()
