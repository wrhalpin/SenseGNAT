from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sensegnat.ingestion.zeek_conn_adapter import ZeekConnLogAdapter


def _write_log(tmp_path: Path, body: str, fields: str | None = None) -> Path:
    """Write a minimal conn.log with standard headers and the given data rows."""
    default_fields = (
        "ts\tuid\tid.orig_h\tid.orig_p\tid.resp_h\tid.resp_p\t"
        "proto\tservice\tduration\torig_bytes\tresp_bytes\tconn_state"
    )
    p = tmp_path / "conn.log"
    p.write_text(
        "#separator \\x09\n"
        "#empty_field\t(empty)\n"
        "#unset_field\t-\n"
        f"#fields\t{fields or default_fields}\n"
        "#types\ttime\tstring\taddr\tport\taddr\tport\tenum\tstring\tinterval\tcount\tcount\tstring\n"
        + body
    )
    return p


_GOOD_ROW = "1705312800.000000\tCxAABB1\t192.168.1.10\t54321\t203.0.113.10\t443\ttcp\tssl\t1.23\t1024\t512\tSF\n"


class TestZeekConnLogAdapter:
    def test_loads_sample_conn_log(self) -> None:
        sample = Path(__file__).parent.parent / "examples" / "sample_conn.log"
        events = list(ZeekConnLogAdapter(sample).fetch_events())
        # Last row has unset destination (-) and should be skipped
        assert len(events) == 6

    def test_field_mapping(self, tmp_path: Path) -> None:
        p = _write_log(tmp_path, _GOOD_ROW)
        event = list(ZeekConnLogAdapter(p).fetch_events())[0]
        assert event.event_id == "CxAABB1"
        assert event.source_host == "192.168.1.10"
        assert event.destination == "203.0.113.10"
        assert event.destination_port == 443
        assert event.protocol == "tcp"
        assert event.bytes_out == 1024
        assert event.bytes_in == 512

    def test_source_user_is_always_none(self, tmp_path: Path) -> None:
        p = _write_log(tmp_path, _GOOD_ROW)
        event = list(ZeekConnLogAdapter(p).fetch_events())[0]
        assert event.source_user is None

    def test_timestamp_parsed_from_epoch_float(self, tmp_path: Path) -> None:
        p = _write_log(tmp_path, _GOOD_ROW)
        event = list(ZeekConnLogAdapter(p).fetch_events())[0]
        assert event.seen_at == datetime.fromtimestamp(1705312800.0, tz=timezone.utc)
        assert event.seen_at.tzinfo == timezone.utc

    def test_protocol_lowercased(self, tmp_path: Path) -> None:
        row = "1705312800.0\tCx1\t192.168.1.1\t1234\t10.0.0.1\t53\tUDP\tdns\t0.01\t64\t128\tSF\n"
        p = _write_log(tmp_path, row)
        event = list(ZeekConnLogAdapter(p).fetch_events())[0]
        assert event.protocol == "udp"

    def test_unset_bytes_default_to_zero(self, tmp_path: Path) -> None:
        row = "1705312800.0\tCx1\t192.168.1.1\t1234\t10.0.0.1\t443\ttcp\t-\t-\t-\t-\tS0\n"
        p = _write_log(tmp_path, row)
        event = list(ZeekConnLogAdapter(p).fetch_events())[0]
        assert event.bytes_out == 0
        assert event.bytes_in == 0

    def test_row_with_unset_destination_is_skipped(self, tmp_path: Path) -> None:
        # Destination '-' means connection never established — skip it
        row = "1705312800.0\tCx1\t192.168.1.1\t54500\t-\t-\ttcp\t-\t-\t-\t-\tS0\n"
        p = _write_log(tmp_path, row)
        assert list(ZeekConnLogAdapter(p).fetch_events()) == []

    def test_comment_and_header_lines_skipped(self, tmp_path: Path) -> None:
        p = _write_log(tmp_path, _GOOD_ROW)
        events = list(ZeekConnLogAdapter(p).fetch_events())
        assert len(events) == 1  # only the one data row

    def test_close_comment_line_skipped(self, tmp_path: Path) -> None:
        body = _GOOD_ROW + "#close\t2024-01-15-10-06-00\n"
        p = _write_log(tmp_path, body)
        events = list(ZeekConnLogAdapter(p).fetch_events())
        assert len(events) == 1

    def test_empty_file_yields_nothing(self, tmp_path: Path) -> None:
        p = tmp_path / "conn.log"
        p.write_text("")
        assert list(ZeekConnLogAdapter(p).fetch_events()) == []

    def test_fields_line_drives_column_order(self, tmp_path: Path) -> None:
        # Fields in non-standard order — parser must use #fields, not position
        fields = "ts\tuid\tid.resp_h\tid.resp_p\tid.orig_h\tid.orig_p\tproto\torig_bytes\tresp_bytes"
        row = "1705312800.0\tCx1\t10.0.0.99\t8080\t192.168.1.5\t55000\ttcp\t2048\t1024\n"
        p = _write_log(tmp_path, row, fields=fields)
        event = list(ZeekConnLogAdapter(p).fetch_events())[0]
        assert event.source_host == "192.168.1.5"
        assert event.destination == "10.0.0.99"
        assert event.destination_port == 8080

    def test_multiple_rows_all_parsed(self, tmp_path: Path) -> None:
        body = (
            "1705312800.0\tCx1\t192.168.1.1\t1111\t10.0.0.1\t443\ttcp\tssl\t1.0\t100\t50\tSF\n"
            "1705312860.0\tCx2\t192.168.1.2\t2222\t10.0.0.2\t80\ttcp\thttp\t0.5\t200\t100\tSF\n"
            "1705312920.0\tCx3\t192.168.1.3\t3333\t10.0.0.3\t53\tudp\tdns\t0.01\t64\t128\tSF\n"
        )
        p = _write_log(tmp_path, body)
        events = list(ZeekConnLogAdapter(p).fetch_events())
        assert len(events) == 3
        assert events[0].destination == "10.0.0.1"
        assert events[1].protocol == "tcp"
        assert events[2].protocol == "udp"
