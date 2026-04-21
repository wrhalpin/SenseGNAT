from __future__ import annotations

"""End-to-end integration tests for SenseGNATService.run_once().

These tests exercise the full pipeline: policy loading → profile building →
rarity detection → peer-deviation detection → narrative building → connector
output.  They use in-memory stores (no settings arg) so they run without
touching the filesystem.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pytest

from sensegnat.api.service import SenseGNATService
from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.policy.engine import PolicyEngine


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event(
    event_id: str,
    source_user: str,
    destination: str,
    port: int = 443,
    source_host: str = "host-1",
    protocol: str = "tcp",
) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id=event_id,
        seen_at=datetime.now(timezone.utc),
        source_host=source_host,
        source_user=source_user,
        destination=destination,
        destination_port=port,
        protocol=protocol,
    )


class _FixedAdapter(EventAdapter):
    def __init__(self, events: list[NormalizedNetworkEvent]) -> None:
        self._events = events

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        return self._events


_POLICY_YAML = """\
groups:
  engineering:
    members: [alice, bob]
    allowed_destinations:
      - 203.0.113.10
    allowed_ports: [22, 443]
    allowed_protocols: [tcp]

subjects:
  alice:
    peer_group: engineering
    allowed_destinations:
      - 198.51.100.44
  bob:
    peer_group: engineering
"""


@pytest.fixture
def policy_engine(tmp_path: Path) -> PolicyEngine:
    p = tmp_path / "policies.yaml"
    p.write_text(_POLICY_YAML)
    return PolicyEngine.from_yaml(p)


def _findings(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("type") == "indicator"]


def _narratives(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("type") == "note"]


def _records_by_type(records: list[dict], record_type: str) -> list[dict]:
    # Map legacy record_type labels to STIX type field for backwards compat
    stix_type = {"anomaly-finding": "indicator", "risk-narrative": "note"}.get(
        record_type, record_type
    )
    return [r for r in records if r.get("type") == stix_type]


# ── Basic pipeline smoke test ─────────────────────────────────────────────────

def test_run_once_returns_list() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([]))
    assert service.run_once() == []


def test_no_findings_when_no_events() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([]))
    assert service.run_once() == []


# ── Rarity detection ──────────────────────────────────────────────────────────

def test_no_rarity_finding_on_first_event_without_existing_profile() -> None:
    # RareDestinationDetector returns None when profile is None (no history yet)
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "198.51.100.99"),
    ]))
    findings = _records_by_type(service.run_once(), "anomaly-finding")
    assert findings == []


def test_rarity_finding_fires_against_existing_profile() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "203.0.113.10"),
    ]))
    service.run_once()   # first run builds alice's profile

    service.adapter = _FixedAdapter([
        _event("e2", "alice", "198.51.100.99"),  # new destination
    ])
    records = service.run_once()
    findings = _records_by_type(records, "anomaly-finding")
    assert len(findings) == 1
    assert findings[0]["x_gnat_signature"] == "rare-destination"
    assert findings[0]["x_sensegnat_subject_id"] == "alice"


def test_no_rarity_finding_for_known_destination() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "203.0.113.10"),
    ]))
    service.run_once()

    service.adapter = _FixedAdapter([
        _event("e2", "alice", "203.0.113.10"),  # same destination — not rare
    ])
    findings = _records_by_type(service.run_once(), "anomaly-finding")
    assert findings == []


# ── Policy seeding suppresses rarity ─────────────────────────────────────────

def test_policy_seeded_destination_not_flagged_as_rare(
    policy_engine: PolicyEngine,
) -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "203.0.113.10"),
    ]))
    service.policy_engine = policy_engine
    service.run_once()  # seeds alice's profile with policy-allowed 203.0.113.10 + 198.51.100.44

    # Second run: alice contacts a policy-seeded destination she's never actually visited
    service.adapter = _FixedAdapter([
        _event("e2", "alice", "198.51.100.44"),
    ])
    findings = _records_by_type(service.run_once(), "anomaly-finding")
    assert findings == []


# ── Peer deviation detection ──────────────────────────────────────────────────

def test_peer_deviation_fires_when_destination_unique_to_subject(
    policy_engine: PolicyEngine,
) -> None:
    # alice and bob are both in engineering; bob contacts only 203.0.113.10
    # alice contacts 10.99.99.99 which bob has never seen → peer deviation
    service = SenseGNATService(
        adapter=_FixedAdapter([
            _event("e1", "alice", "10.99.99.99"),
            _event("e2", "bob", "203.0.113.10"),
        ]),
    )
    service.policy_engine = policy_engine
    records = service.run_once()
    peer_findings = [
        r for r in _records_by_type(records, "anomaly-finding")
        if r.get("x_gnat_signature") == "peer-deviation"
    ]
    assert len(peer_findings) == 1
    assert peer_findings[0]["x_sensegnat_subject_id"] == "alice"


def test_peer_deviation_does_not_fire_when_destination_seen_by_peers(
    policy_engine: PolicyEngine,
) -> None:
    # both alice and bob contact the same destination → no peer deviation
    service = SenseGNATService(
        adapter=_FixedAdapter([
            _event("e1", "alice", "203.0.113.10"),
            _event("e2", "bob", "203.0.113.10"),
        ]),
    )
    service.policy_engine = policy_engine
    records = service.run_once()
    peer_findings = [
        r for r in _records_by_type(records, "anomaly-finding")
        if r.get("x_gnat_signature") == "peer-deviation"
    ]
    assert peer_findings == []


# ── Narrative generation ──────────────────────────────────────────────────────

def test_narrative_emitted_when_findings_exist() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "203.0.113.10"),
    ]))
    service.run_once()  # build profile

    service.adapter = _FixedAdapter([_event("e2", "alice", "198.51.100.99")])
    records = service.run_once()
    narratives = _records_by_type(records, "risk-narrative")
    assert len(narratives) == 1
    assert narratives[0]["x_sensegnat_subject_id"] == "alice"
    assert narratives[0]["x_sensegnat_finding_count"] == 1


def test_no_narrative_when_no_findings() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "203.0.113.10"),
    ]))
    service.run_once()  # build profile

    service.adapter = _FixedAdapter([_event("e2", "alice", "203.0.113.10")])
    records = service.run_once()
    assert _records_by_type(records, "risk-narrative") == []


def test_separate_narratives_per_subject() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "10.0.0.1"),
        _event("e2", "bob", "10.0.0.1", source_host="host-2"),
    ]))
    service.run_once()  # build profiles for alice and bob

    service.adapter = _FixedAdapter([
        _event("e3", "alice", "198.51.100.1"),
        _event("e4", "bob", "198.51.100.2", source_host="host-2"),
    ])
    records = service.run_once()
    narratives = _records_by_type(records, "risk-narrative")
    subjects = {n["x_sensegnat_subject_id"] for n in narratives}
    assert subjects == {"alice", "bob"}


# ── Profile accumulation across runs ─────────────────────────────────────────

def test_profile_accumulates_destinations_across_runs() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "10.0.0.1"),
    ]))
    service.run_once()  # alice's profile: {10.0.0.1}

    service.adapter = _FixedAdapter([_event("e2", "alice", "10.0.0.2")])
    service.run_once()  # alice's profile should now be {10.0.0.1, 10.0.0.2}

    # Third run: 10.0.0.1 was seen in run 1 — should NOT be flagged as rare
    service.adapter = _FixedAdapter([_event("e3", "alice", "10.0.0.1")])
    findings = _records_by_type(service.run_once(), "anomaly-finding")
    assert findings == []


def test_new_destination_still_rare_after_accumulation() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "10.0.0.1"),
    ]))
    service.run_once()
    service.adapter = _FixedAdapter([_event("e2", "alice", "10.0.0.2")])
    service.run_once()

    # Third run: brand-new destination should still fire
    service.adapter = _FixedAdapter([_event("e3", "alice", "198.51.100.99")])
    findings = _records_by_type(service.run_once(), "anomaly-finding")
    assert len(findings) == 1
    assert findings[0]["x_gnat_signature"] == "rare-destination"


# ── Output record shape ───────────────────────────────────────────────────────

def test_finding_record_has_required_fields() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "10.0.0.1"),
    ]))
    service.run_once()
    service.adapter = _FixedAdapter([_event("e2", "alice", "198.51.100.99")])
    records = service.run_once()
    finding = _records_by_type(records, "anomaly-finding")[0]
    for field in ("type", "spec_version", "id", "name", "pattern", "pattern_type",
                  "valid_from", "indicator_types", "confidence",
                  "x_gnat_sensor_type", "x_gnat_sensor_id", "x_gnat_signature",
                  "x_sensegnat_finding_id", "x_sensegnat_score", "x_sensegnat_severity",
                  "x_sensegnat_summary", "x_sensegnat_subject_id"):
        assert field in finding, f"missing field: {field}"


def test_narrative_record_has_required_fields() -> None:
    service = SenseGNATService(adapter=_FixedAdapter([
        _event("e1", "alice", "10.0.0.1"),
    ]))
    service.run_once()
    service.adapter = _FixedAdapter([_event("e2", "alice", "198.51.100.99")])
    records = service.run_once()
    narrative = _records_by_type(records, "risk-narrative")[0]
    for field in ("type", "spec_version", "id", "content",
                  "x_gnat_sensor_id", "x_sensegnat_subject_id", "x_sensegnat_finding_count",
                  "x_sensegnat_severity", "x_sensegnat_score", "x_sensegnat_finding_types"):
        assert field in narrative, f"missing field: {field}"
