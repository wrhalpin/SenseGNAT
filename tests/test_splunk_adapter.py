from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from sensegnat.ingestion.splunk_adapter import SplunkEventAdapter
from sensegnat.models.events import NormalizedNetworkEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUERY = "search index=network | fields _time, src, dest, dest_port"
_HOST = "splunk.test"


def _record(**kwargs) -> dict:
    base = {
        "_time": "1705312800.0",
        "_cd": "1:10001",
        "src": "192.168.1.10",
        "dest": "203.0.113.10",
        "dest_port": "443",
        "transport": "tcp",
        "bytes_out": "1024",
        "bytes_in": "512",
    }
    base.update(kwargs)
    return base


class _FakeMessage:
    """Stand-in for splunklib.results.Message so isinstance() works."""

    def __init__(self, type_: str, message: str) -> None:
        self.type = type_
        self.message = message


def _make_splunk_mocks(pages: list[list[dict]]):
    """Return (mock_client, mock_results, mock_job) for patching."""
    mock_job = MagicMock()
    mock_service = MagicMock()
    mock_service.jobs.create.return_value = mock_job

    page_iter = iter(pages)

    def reader_side_effect(stream):
        try:
            return iter(next(page_iter))
        except StopIteration:
            return iter([])

    mock_client = MagicMock()
    mock_client.connect.return_value = mock_service

    mock_results = MagicMock()
    mock_results.Message = _FakeMessage
    mock_results.JSONResultsReader.side_effect = reader_side_effect

    return mock_client, mock_results, mock_job


def _fetch(records: list[dict], **adapter_kwargs) -> list[NormalizedNetworkEvent]:
    """Run fetch_events() against a single-page mock; collect results."""
    adapter = SplunkEventAdapter(spl_query=_QUERY, host=_HOST, **adapter_kwargs)
    mock_client, mock_results, _ = _make_splunk_mocks([records, []])
    with (
        patch("sensegnat.ingestion.splunk_adapter._splunk_client", mock_client),
        patch("sensegnat.ingestion.splunk_adapter._splunk_results", mock_results),
    ):
        return list(adapter.fetch_events())


# ---------------------------------------------------------------------------
# Field mapping — CIM primary fields
# ---------------------------------------------------------------------------


class TestFieldMapping:
    def test_source_host_from_src(self):
        events = _fetch([_record(src="10.0.0.1")])
        assert events[0].source_host == "10.0.0.1"

    def test_destination_from_dest(self):
        events = _fetch([_record(dest="172.16.0.1")])
        assert events[0].destination == "172.16.0.1"

    def test_destination_port_from_dest_port(self):
        events = _fetch([_record(dest_port="8443")])
        assert events[0].destination_port == 8443

    def test_destination_port_is_int(self):
        events = _fetch([_record(dest_port="80")])
        assert isinstance(events[0].destination_port, int)

    def test_protocol_from_transport(self):
        events = _fetch([_record(transport="TCP")])
        assert events[0].protocol == "tcp"

    def test_bytes_out_from_bytes_out(self):
        events = _fetch([_record(bytes_out="2048")])
        assert events[0].bytes_out == 2048

    def test_bytes_in_from_bytes_in(self):
        events = _fetch([_record(bytes_in="1024")])
        assert events[0].bytes_in == 1024

    def test_event_id_from_cd(self):
        events = _fetch([_record(**{"_cd": "3:99999"})])
        assert events[0].event_id == "3:99999"

    def test_source_user_from_user(self):
        events = _fetch([_record(user="alice")])
        assert events[0].source_user == "alice"

    def test_source_user_none_when_absent(self):
        r = _record()
        r.pop("user", None)
        events = _fetch([r])
        assert events[0].source_user is None


# ---------------------------------------------------------------------------
# Field fallbacks — vendor-specific names
# ---------------------------------------------------------------------------


class TestFieldFallbacks:
    def test_src_ip_falls_back_to_source_host(self):
        r = {k: v for k, v in _record().items() if k != "src"}
        r["src_ip"] = "10.1.2.3"
        events = _fetch([r])
        assert events[0].source_host == "10.1.2.3"

    def test_source_ip_falls_back_to_source_host(self):
        r = {k: v for k, v in _record().items() if k not in ("src", "src_ip")}
        r["source_ip"] = "10.1.2.4"
        events = _fetch([r])
        assert events[0].source_host == "10.1.2.4"

    def test_dest_ip_falls_back_to_destination(self):
        r = {k: v for k, v in _record().items() if k != "dest"}
        r["dest_ip"] = "10.2.3.4"
        events = _fetch([r])
        assert events[0].destination == "10.2.3.4"

    def test_destination_port_fallback(self):
        r = {k: v for k, v in _record().items() if k != "dest_port"}
        r["destination_port"] = "9000"
        events = _fetch([r])
        assert events[0].destination_port == 9000

    def test_protocol_fallback_to_protocol_field(self):
        r = {k: v for k, v in _record().items() if k != "transport"}
        r["protocol"] = "UDP"
        events = _fetch([r])
        assert events[0].protocol == "udp"

    def test_protocol_fallback_to_proto(self):
        r = {k: v for k, v in _record().items() if k not in ("transport", "protocol")}
        r["proto"] = "ICMP"
        events = _fetch([r])
        assert events[0].protocol == "icmp"

    def test_bytes_out_fallback_bytes_sent(self):
        r = {k: v for k, v in _record().items() if k != "bytes_out"}
        r["bytes_sent"] = "4096"
        events = _fetch([r])
        assert events[0].bytes_out == 4096

    def test_bytes_out_fallback_out_bytes(self):
        r = {k: v for k, v in _record().items() if k not in ("bytes_out", "bytes_sent")}
        r["out_bytes"] = "8192"
        events = _fetch([r])
        assert events[0].bytes_out == 8192

    def test_bytes_in_fallback_bytes_received(self):
        r = {k: v for k, v in _record().items() if k != "bytes_in"}
        r["bytes_received"] = "2048"
        events = _fetch([r])
        assert events[0].bytes_in == 2048

    def test_source_user_fallback_src_user(self):
        r = _record(src_user="bob")
        events = _fetch([r])
        assert events[0].source_user == "bob"


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


class TestTimestampParsing:
    def test_epoch_float_string(self):
        events = _fetch([_record(**{"_time": "1705312800.0"})])
        expected = datetime.fromtimestamp(1705312800.0, tz=timezone.utc)
        assert events[0].seen_at == expected

    def test_epoch_integer_string(self):
        events = _fetch([_record(**{"_time": "1705312800"})])
        expected = datetime.fromtimestamp(1705312800, tz=timezone.utc)
        assert events[0].seen_at == expected

    def test_seen_at_is_utc_aware(self):
        events = _fetch([_record()])
        assert events[0].seen_at.tzinfo is not None

    def test_missing_time_falls_back_to_now(self):
        r = _record()
        del r["_time"]
        events = _fetch([r])
        assert (datetime.now(tz=timezone.utc) - events[0].seen_at).total_seconds() < 5


# ---------------------------------------------------------------------------
# Protocol normalisation
# ---------------------------------------------------------------------------


class TestProtocolNormalisation:
    def test_tcp_uppercased_lowercased(self):
        assert _fetch([_record(transport="TCP")])[0].protocol == "tcp"

    def test_udp_uppercased_lowercased(self):
        assert _fetch([_record(transport="UDP")])[0].protocol == "udp"

    def test_empty_protocol_stays_empty(self):
        r = {k: v for k, v in _record().items() if k not in ("transport", "protocol", "proto")}
        assert _fetch([r])[0].protocol == ""


# ---------------------------------------------------------------------------
# Bytes defaults
# ---------------------------------------------------------------------------


class TestBytesDefaults:
    def test_bytes_out_defaults_to_zero(self):
        r = {k: v for k, v in _record().items() if k not in ("bytes_out", "bytes_sent", "out_bytes")}
        assert _fetch([r])[0].bytes_out == 0

    def test_bytes_in_defaults_to_zero(self):
        r = {k: v for k, v in _record().items() if k not in ("bytes_in", "bytes_received", "in_bytes")}
        assert _fetch([r])[0].bytes_in == 0


# ---------------------------------------------------------------------------
# Event ID
# ---------------------------------------------------------------------------


class TestEventId:
    def test_uuid_generated_when_cd_absent(self):
        r = {k: v for k, v in _record().items() if k != "_cd"}
        events = _fetch([r])
        assert len(events[0].event_id) == 36  # UUID format

    def test_cd_used_when_present(self):
        events = _fetch([_record(**{"_cd": "5:12345"})])
        assert events[0].event_id == "5:12345"


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------


class TestSkipConditions:
    def test_missing_src_skipped(self):
        r = {k: v for k, v in _record().items() if k not in ("src", "src_ip", "source_ip", "source")}
        assert _fetch([r]) == []

    def test_empty_src_skipped(self):
        assert _fetch([_record(src="")]) == []

    def test_missing_dest_skipped(self):
        r = {k: v for k, v in _record().items() if k not in ("dest", "dest_ip", "destination_ip", "destination")}
        assert _fetch([r]) == []

    def test_empty_dest_skipped(self):
        assert _fetch([_record(dest="")]) == []

    def test_missing_dest_port_skipped(self):
        r = {k: v for k, v in _record().items() if k not in ("dest_port", "destination_port")}
        assert _fetch([r]) == []

    def test_invalid_dest_port_skipped(self):
        assert _fetch([_record(dest_port="not-a-number")]) == []


# ---------------------------------------------------------------------------
# Multiple records
# ---------------------------------------------------------------------------


class TestMultipleRecords:
    def test_all_valid_records_parsed(self):
        records = [_record(**{"_cd": f"1:{i}", "dest_port": str(i + 1)}) for i in range(5)]
        events = _fetch(records)
        assert len(events) == 5

    def test_mixed_valid_and_invalid(self):
        records = [
            _record(**{"_cd": "1:1"}),
            _record(dest=""),  # skipped
            _record(**{"_cd": "1:3"}),
        ]
        events = _fetch(records)
        assert len(events) == 2


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_second_page_fetched_when_first_full(self):
        page1 = [_record(**{"_cd": f"1:{i}"}) for i in range(3)]
        page2 = [_record(**{"_cd": f"1:{i}"}) for i in range(3, 5)]

        adapter = SplunkEventAdapter(spl_query=_QUERY, host=_HOST, page_size=3)
        mock_client, mock_results, mock_job = _make_splunk_mocks([page1, page2, []])

        with (
            patch("sensegnat.ingestion.splunk_adapter._splunk_client", mock_client),
            patch("sensegnat.ingestion.splunk_adapter._splunk_results", mock_results),
        ):
            events = list(adapter.fetch_events())

        assert len(events) == 5

    def test_offset_increments_by_raw_page_size(self):
        page1 = [_record(**{"_cd": f"1:{i}"}) for i in range(4)]

        adapter = SplunkEventAdapter(spl_query=_QUERY, host=_HOST, page_size=4)
        mock_client, mock_results, mock_job = _make_splunk_mocks([page1, []])

        with (
            patch("sensegnat.ingestion.splunk_adapter._splunk_client", mock_client),
            patch("sensegnat.ingestion.splunk_adapter._splunk_results", mock_results),
        ):
            list(adapter.fetch_events())

        calls = mock_job.results.call_args_list
        assert calls[0][1]["offset"] == 0
        assert calls[1][1]["offset"] == 4

    def test_max_results_stops_early(self):
        records = [_record(**{"_cd": f"1:{i}"}) for i in range(10)]
        events = _fetch(records, max_results=3)
        assert len(events) == 3

    def test_max_results_none_drains_all(self):
        records = [_record(**{"_cd": f"1:{i}"}) for i in range(8)]
        events = _fetch(records, max_results=None)
        assert len(events) == 8

    def test_empty_first_page_yields_nothing(self):
        events = _fetch([])
        assert events == []


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_token_auth_passes_token_to_connect(self):
        adapter = SplunkEventAdapter(
            spl_query=_QUERY, host=_HOST, token="my-bearer-token"
        )
        mock_client, mock_results, _ = _make_splunk_mocks([[]])
        with (
            patch("sensegnat.ingestion.splunk_adapter._splunk_client", mock_client),
            patch("sensegnat.ingestion.splunk_adapter._splunk_results", mock_results),
        ):
            list(adapter.fetch_events())

        call_kwargs = mock_client.connect.call_args[1]
        assert call_kwargs.get("token") == "my-bearer-token"
        assert "username" not in call_kwargs
        assert "password" not in call_kwargs

    def test_username_password_auth(self):
        adapter = SplunkEventAdapter(
            spl_query=_QUERY, host=_HOST, username="admin", password="secret"
        )
        mock_client, mock_results, _ = _make_splunk_mocks([[]])
        with (
            patch("sensegnat.ingestion.splunk_adapter._splunk_client", mock_client),
            patch("sensegnat.ingestion.splunk_adapter._splunk_results", mock_results),
        ):
            list(adapter.fetch_events())

        call_kwargs = mock_client.connect.call_args[1]
        assert call_kwargs.get("username") == "admin"
        assert call_kwargs.get("password") == "secret"
        assert "token" not in call_kwargs

    def test_token_takes_priority_over_username_password(self):
        adapter = SplunkEventAdapter(
            spl_query=_QUERY,
            host=_HOST,
            token="tok",
            username="admin",
            password="secret",
        )
        mock_client, mock_results, _ = _make_splunk_mocks([[]])
        with (
            patch("sensegnat.ingestion.splunk_adapter._splunk_client", mock_client),
            patch("sensegnat.ingestion.splunk_adapter._splunk_results", mock_results),
        ):
            list(adapter.fetch_events())

        call_kwargs = mock_client.connect.call_args[1]
        assert call_kwargs.get("token") == "tok"
        assert "username" not in call_kwargs


# ---------------------------------------------------------------------------
# SDK unavailable
# ---------------------------------------------------------------------------


class TestSdkUnavailable:
    def test_raises_import_error_with_helpful_message(self):
        adapter = SplunkEventAdapter(spl_query=_QUERY, host=_HOST)
        with patch("sensegnat.ingestion.splunk_adapter._splunk_client", None):
            with pytest.raises(ImportError, match="splunk-sdk"):
                list(adapter.fetch_events())

    def test_adapter_constructable_without_sdk(self):
        # Construction must not raise even when splunklib is absent
        with patch("sensegnat.ingestion.splunk_adapter._splunk_client", None):
            SplunkEventAdapter(spl_query=_QUERY, host=_HOST)


# ---------------------------------------------------------------------------
# Splunk Message objects in results are skipped
# ---------------------------------------------------------------------------


class TestSplunkMessages:
    def test_message_objects_skipped_not_yielded(self):
        records = [
            _FakeMessage("INFO", "some diagnostic"),
            _record(**{"_cd": "1:1"}),
            _FakeMessage("WARN", "another message"),
            _record(**{"_cd": "1:2"}),
        ]
        adapter = SplunkEventAdapter(spl_query=_QUERY, host=_HOST)
        mock_client, mock_results, _ = _make_splunk_mocks([records, []])
        with (
            patch("sensegnat.ingestion.splunk_adapter._splunk_client", mock_client),
            patch("sensegnat.ingestion.splunk_adapter._splunk_results", mock_results),
        ):
            events = list(adapter.fetch_events())

        assert len(events) == 2
