from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sensegnat.ingestion.sample_adapter import SampleEventAdapter
from sensegnat.api.service import SenseGNATService
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.ingestion.base import EventAdapter


class _FixedAdapter(EventAdapter):
    def __init__(self, events: list[NormalizedNetworkEvent]) -> None:
        self._events = events

    def fetch_events(self):
        return iter(self._events)


def _event(
    host: str,
    destination: str,
    investigation_hint: str | None = None,
) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id=f"e-{host}-{destination}",
        seen_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        source_host=host,
        source_user=None,
        destination=destination,
        destination_port=443,
        protocol="tcp",
        investigation_hint=investigation_hint,
    )


class TestGroupingEnvelope:
    def test_untagged_findings_produce_no_grouping(self) -> None:
        # Two runs: first builds the profile, second detects a novel destination
        adapter = _FixedAdapter([_event("host-1", "10.0.0.1")])
        svc = SenseGNATService(adapter)
        svc.run_once()  # build baseline

        adapter._events = [_event("host-1", "10.0.0.2")]  # novel
        result = svc.run_once()
        groupings = [r for r in result if r.get("type") == "grouping"]
        assert groupings == []

    def test_tagged_findings_produce_one_grouping_per_investigation(self) -> None:
        adapter = _FixedAdapter([_event("host-1", "10.0.0.1")])
        svc = SenseGNATService(adapter)
        svc._investigation_lookup_enabled = True
        svc.run_once()  # baseline

        # Enable hint so enrichment fires without needing the GNAT API
        adapter._events = [_event("host-1", "10.0.0.2", investigation_hint="IC-2026-0001")]
        result = svc.run_once()
        groupings = [r for r in result if r.get("type") == "grouping"]
        assert len(groupings) == 1
        assert groupings[0]["x_gnat_investigation_id"] == "IC-2026-0001"

    def test_two_investigations_produce_two_groupings(self) -> None:
        adapter = _FixedAdapter([
            _event("host-1", "10.0.0.1"),
            _event("host-2", "10.0.0.3"),
        ])
        svc = SenseGNATService(adapter)
        svc._investigation_lookup_enabled = True
        svc.run_once()  # baseline

        adapter._events = [
            _event("host-1", "10.0.0.2", investigation_hint="IC-2026-0001"),
            _event("host-2", "10.0.0.4", investigation_hint="IC-2026-0002"),
        ]
        result = svc.run_once()
        groupings = [r for r in result if r.get("type") == "grouping"]
        inv_ids = {g["x_gnat_investigation_id"] for g in groupings}
        assert inv_ids == {"IC-2026-0001", "IC-2026-0002"}

    def test_grouping_object_refs_point_to_emitted_stix_ids(self) -> None:
        adapter = _FixedAdapter([_event("host-1", "10.0.0.1")])
        svc = SenseGNATService(adapter)
        svc._investigation_lookup_enabled = True
        svc.run_once()

        adapter._events = [_event("host-1", "10.0.0.2", investigation_hint="IC-001")]
        result = svc.run_once()

        published_ids = {r["id"] for r in result if r.get("type") in ("indicator", "note")}
        groupings = [r for r in result if r.get("type") == "grouping"]
        for g in groupings:
            for ref in g["object_refs"]:
                assert ref in published_ids
