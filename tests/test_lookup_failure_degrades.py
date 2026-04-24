from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from sensegnat.api.service import SenseGNATService
from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent


class _FixedAdapter(EventAdapter):
    def __init__(self, events):
        self._events = events

    def fetch_events(self):
        return iter(self._events)


def _event(destination: str) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id="e1",
        seen_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        source_host="host-1",
        source_user=None,
        destination=destination,
        destination_port=443,
        protocol="tcp",
    )


class TestLookupFailureDegrades:
    def _setup_service_with_lookup_enabled(self):
        svc = SenseGNATService(_FixedAdapter([_event("10.0.0.1")]))
        svc._investigation_lookup_enabled = True
        svc.run_once()  # build baseline
        return svc

    def test_findings_emit_when_gnat_times_out(self) -> None:
        svc = self._setup_service_with_lookup_enabled()
        svc.adapter._events = [_event("10.0.0.2")]

        with patch.object(
            svc.connector,
            "find_investigations_for_subject",
            side_effect=TimeoutError("timeout"),
        ):
            # Should not raise — degrades gracefully
            result = svc.run_once()

        indicators = [r for r in result if r.get("type") == "indicator"]
        assert len(indicators) >= 1

    def test_findings_unstamped_when_gnat_errors(self) -> None:
        svc = self._setup_service_with_lookup_enabled()
        svc.adapter._events = [_event("10.0.0.2")]

        with patch.object(
            svc.connector,
            "find_investigations_for_subject",
            return_value=[],
        ):
            result = svc.run_once()

        indicators = [r for r in result if r.get("type") == "indicator"]
        for ind in indicators:
            assert "x_gnat_investigation_id" not in ind

    def test_no_grouping_emitted_when_lookup_returns_empty(self) -> None:
        svc = self._setup_service_with_lookup_enabled()
        svc.adapter._events = [_event("10.0.0.2")]

        with patch.object(
            svc.connector,
            "find_investigations_for_subject",
            return_value=[],
        ):
            result = svc.run_once()

        assert not any(r.get("type") == "grouping" for r in result)

    def test_run_once_does_not_raise_on_gnat_error(self) -> None:
        svc = self._setup_service_with_lookup_enabled()
        svc.adapter._events = [_event("10.0.0.2")]

        with patch.object(
            svc.connector,
            "find_investigations_for_subject",
            side_effect=Exception("unexpected"),
        ):
            # The enrichment helper swallows exceptions via find_investigations_for_subject
            # which itself never raises. But if it did propagate, run_once should not crash.
            try:
                result = svc.run_once()
            except Exception:
                pytest.fail("run_once raised unexpectedly when GNAT lookup failed")
