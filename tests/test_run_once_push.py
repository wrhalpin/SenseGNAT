from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from sensegnat.api.service import SenseGNATService
from sensegnat.connectors.gnat_connector import GNATConnector, PushResult
from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent


class _FixedAdapter(EventAdapter):
    def __init__(self, events: list[NormalizedNetworkEvent]) -> None:
        self._events = events

    def fetch_events(self):
        return iter(self._events)


def _event(host: str, destination: str) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id=f"e-{host}-{destination}",
        seen_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        source_host=host,
        source_user=None,
        destination=destination,
        destination_port=443,
        protocol="tcp",
    )


class TestPushObjects:
    def test_empty_list_returns_empty_result_without_network(self) -> None:
        connector = GNATConnector()
        connector._push_bundle = MagicMock()  # would explode if called

        result = connector.push_objects([])
        assert result.pushed == 0
        assert result.errors == []
        connector._push_bundle.assert_not_called()

    def test_delegates_to_push_bundle(self) -> None:
        connector = GNATConnector()
        connector._push_bundle = MagicMock(return_value=PushResult(pushed=2))
        objects = [{"type": "indicator", "id": "indicator--1"},
                   {"type": "note", "id": "note--1"}]

        result = connector.push_objects(objects)
        assert result.pushed == 2
        connector._push_bundle.assert_called_once_with(objects)

    def test_record_only_connector_skips_push(self) -> None:
        # No base_url/api_key — _push_bundle logs a warning and returns empty
        connector = GNATConnector()
        result = connector.push_objects([{"type": "indicator", "id": "indicator--1"}])
        assert result.pushed == 0
        assert result.errors == []


class TestRunOncePushes:
    def test_run_once_pushes_exactly_the_published_objects(self) -> None:
        adapter = _FixedAdapter([_event("host-1", "10.0.0.1")])
        svc = SenseGNATService(adapter)
        svc.run_once()  # baseline — no findings

        svc.connector._push_bundle = MagicMock(return_value=PushResult(pushed=0))
        adapter._events = [_event("host-1", "10.0.0.2")]  # novel destination
        published = svc.run_once()

        assert published  # sanity: the novel destination produced findings
        svc.connector._push_bundle.assert_called_once_with(published)

    def test_pushed_objects_carry_same_stix_ids_as_returned(self) -> None:
        # The push must send the exact serialized objects — not re-serialized
        # copies with fresh IDs — so Grouping object_refs stay valid.
        adapter = _FixedAdapter([_event("host-1", "10.0.0.1")])
        svc = SenseGNATService(adapter)
        svc.run_once()

        captured: list[list[dict]] = []
        svc.connector._push_bundle = lambda objs: captured.append(objs) or PushResult()
        adapter._events = [_event("host-1", "10.0.0.2")]
        published = svc.run_once()

        assert len(captured) == 1
        assert [o["id"] for o in captured[0]] == [o["id"] for o in published]

    def test_no_push_when_no_findings(self) -> None:
        adapter = _FixedAdapter([_event("host-1", "10.0.0.1")])
        svc = SenseGNATService(adapter)
        svc.connector._push_bundle = MagicMock()

        published = svc.run_once()  # first run builds baseline, no findings
        assert published == []
        svc.connector._push_bundle.assert_not_called()

    def test_record_only_service_run_once_does_not_raise(self) -> None:
        # Default service has an unconfigured connector; push degrades to a
        # logged warning and run_once still returns the serialized STIX.
        adapter = _FixedAdapter([_event("host-1", "10.0.0.1")])
        svc = SenseGNATService(adapter)
        svc.run_once()

        adapter._events = [_event("host-1", "10.0.0.2")]
        published = svc.run_once()
        assert any(o.get("type") == "indicator" for o in published)

    def test_push_failure_does_not_break_run_once(self) -> None:
        adapter = _FixedAdapter([_event("host-1", "10.0.0.1")])
        svc = SenseGNATService(adapter)
        svc.run_once()

        svc.connector._push_bundle = MagicMock(
            return_value=PushResult(errors=["HTTP 500: boom"])
        )
        adapter._events = [_event("host-1", "10.0.0.2")]
        published = svc.run_once()  # must not raise
        assert published
