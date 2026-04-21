from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sensegnat.ingestion.suricata_eve_adapter import SuricataEveAdapter


def _write_eve(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "eve.json"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return p


def _flow(
    *,
    src_ip: str = "192.168.1.10",
    dest_ip: str = "203.0.113.10",
    dest_port: int = 443,
    proto: str = "TCP",
    flow_id: int = 1111111111,
    timestamp: str = "2024-01-15T10:00:00.000000+0000",
    bytes_toserver: int = 1024,
    bytes_toclient: int = 512,
) -> dict:
    return {
        "timestamp": timestamp,
        "flow_id": flow_id,
        "event_type": "flow",
        "src_ip": src_ip,
        "src_port": 54321,
        "dest_ip": dest_ip,
        "dest_port": dest_port,
        "proto": proto,
        "flow": {"bytes_toserver": bytes_toserver, "bytes_toclient": bytes_toclient},
    }


def _alert(**kwargs) -> dict:
    record = _flow(**kwargs)
    record["event_type"] = "alert"
    record["alert"] = {"signature": "ET TEST", "severity": 1}
    return record


class TestSuricataEveAdapter:
    def test_loads_sample_eve_json(self) -> None:
        sample = Path(__file__).parent.parent / "examples" / "sample_eve.json"
        events = list(SuricataEveAdapter(sample).fetch_events())
        # 5 flow + 1 alert = 6; dns and stats records skipped
        assert len(events) == 6

    def test_flow_field_mapping(self, tmp_path: Path) -> None:
        p = _write_eve(tmp_path, [_flow()])
        event = list(SuricataEveAdapter(p).fetch_events())[0]
        assert event.event_id == "1111111111"
        assert event.source_host == "192.168.1.10"
        assert event.destination == "203.0.113.10"
        assert event.destination_port == 443
        assert event.protocol == "tcp"
        assert event.bytes_out == 1024
        assert event.bytes_in == 512

    def test_alert_event_parsed(self, tmp_path: Path) -> None:
        p = _write_eve(tmp_path, [_alert(dest_ip="10.99.99.99", dest_port=8080)])
        events = list(SuricataEveAdapter(p).fetch_events())
        assert len(events) == 1
        assert events[0].destination == "10.99.99.99"
        assert events[0].destination_port == 8080

    def test_source_user_always_none(self, tmp_path: Path) -> None:
        p = _write_eve(tmp_path, [_flow()])
        assert list(SuricataEveAdapter(p).fetch_events())[0].source_user is None

    def test_protocol_lowercased(self, tmp_path: Path) -> None:
        p = _write_eve(tmp_path, [_flow(proto="UDP")])
        assert list(SuricataEveAdapter(p).fetch_events())[0].protocol == "udp"

    def test_timestamp_with_bare_offset_parsed(self, tmp_path: Path) -> None:
        # +0000 without colon — non-standard but common in Suricata output
        p = _write_eve(tmp_path, [_flow(timestamp="2024-01-15T10:00:00.123456+0000")])
        event = list(SuricataEveAdapter(p).fetch_events())[0]
        assert event.seen_at.tzinfo is not None
        assert event.seen_at.year == 2024

    def test_timestamp_with_standard_offset_parsed(self, tmp_path: Path) -> None:
        p = _write_eve(tmp_path, [_flow(timestamp="2024-06-01T14:30:00.000000+00:00")])
        event = list(SuricataEveAdapter(p).fetch_events())[0]
        assert event.seen_at == datetime(2024, 6, 1, 14, 30, 0, tzinfo=timezone.utc)

    def test_timestamp_with_z_suffix_parsed(self, tmp_path: Path) -> None:
        p = _write_eve(tmp_path, [_flow(timestamp="2024-01-15T10:00:00Z")])
        event = list(SuricataEveAdapter(p).fetch_events())[0]
        assert event.seen_at.tzinfo == timezone.utc

    def test_bytes_default_to_zero_when_flow_absent(self, tmp_path: Path) -> None:
        record = _flow()
        del record["flow"]
        p = _write_eve(tmp_path, [record])
        event = list(SuricataEveAdapter(p).fetch_events())[0]
        assert event.bytes_out == 0
        assert event.bytes_in == 0

    def test_event_id_from_flow_id(self, tmp_path: Path) -> None:
        p = _write_eve(tmp_path, [_flow(flow_id=9876543210)])
        assert list(SuricataEveAdapter(p).fetch_events())[0].event_id == "9876543210"

    def test_event_id_generated_when_flow_id_absent(self, tmp_path: Path) -> None:
        record = _flow()
        del record["flow_id"]
        p = _write_eve(tmp_path, [record])
        event_id = list(SuricataEveAdapter(p).fetch_events())[0].event_id
        assert event_id  # non-empty UUID

    def test_dns_event_skipped(self, tmp_path: Path) -> None:
        dns = {"timestamp": "2024-01-15T10:00:00Z", "event_type": "dns",
               "src_ip": "192.168.1.1", "dest_ip": "8.8.8.8", "dest_port": 53,
               "proto": "UDP", "dns": {"rrname": "example.com"}}
        p = _write_eve(tmp_path, [dns])
        assert list(SuricataEveAdapter(p).fetch_events()) == []

    def test_stats_event_skipped(self, tmp_path: Path) -> None:
        stats = {"timestamp": "2024-01-15T10:00:00Z", "event_type": "stats",
                 "stats": {"uptime": 3600}}
        p = _write_eve(tmp_path, [stats])
        assert list(SuricataEveAdapter(p).fetch_events()) == []

    def test_invalid_json_lines_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "eve.json"
        p.write_text(
            '{"this": "is valid"}\n'
            "not json at all\n"
            + json.dumps(_flow()) + "\n"
        )
        events = list(SuricataEveAdapter(p).fetch_events())
        # First record is valid JSON but wrong event_type; third is a flow
        assert len(events) == 1

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "eve.json"
        p.write_text("\n\n" + json.dumps(_flow()) + "\n\n")
        assert len(list(SuricataEveAdapter(p).fetch_events())) == 1

    def test_empty_file_yields_nothing(self, tmp_path: Path) -> None:
        p = tmp_path / "eve.json"
        p.write_text("")
        assert list(SuricataEveAdapter(p).fetch_events()) == []

    def test_record_missing_dest_ip_skipped(self, tmp_path: Path) -> None:
        record = _flow()
        del record["dest_ip"]
        p = _write_eve(tmp_path, [record])
        assert list(SuricataEveAdapter(p).fetch_events()) == []

    def test_multiple_records_all_parsed(self, tmp_path: Path) -> None:
        records = [
            _flow(dest_ip="10.0.0.1", dest_port=443, flow_id=1),
            _alert(dest_ip="10.0.0.2", dest_port=80, flow_id=2),
            _flow(dest_ip="10.0.0.3", dest_port=22, flow_id=3, proto="TCP"),
        ]
        p = _write_eve(tmp_path, records)
        events = list(SuricataEveAdapter(p).fetch_events())
        assert len(events) == 3
        assert {e.destination for e in events} == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}
