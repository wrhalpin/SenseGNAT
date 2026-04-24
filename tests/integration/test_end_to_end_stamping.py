from __future__ import annotations

"""End-to-end integration test for investigation context stamping.

Exercises all three attachment paths in a single run_once() call:
  Path A — PolicyViolationDetector stamps findings from the policy rule.
  Path B — Enrichment pass stamps findings via telemetry hint.
  Path C — No match; findings emit without investigation context.
"""

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from sensegnat.api.service import SenseGNATService
from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent


class _FixedAdapter(EventAdapter):
    def __init__(self, events: list[NormalizedNetworkEvent]) -> None:
        self._events = events

    def fetch_events(self):
        return iter(self._events)


def _event(
    host: str,
    destination: str,
    port: int = 443,
    investigation_hint: str | None = None,
) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id=f"{host}-{destination}",
        seen_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        source_host=host,
        source_user=None,
        destination=destination,
        destination_port=port,
        protocol="tcp",
        investigation_hint=investigation_hint,
    )


@pytest.fixture()
def policy_file(tmp_path: Path) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(textwrap.dedent("""
        subjects:
          host-policy:
            allowed_destinations: ["10.0.0.1"]
            allowed_ports: [443]
            investigation_id: "IC-POLICY-001"
            investigation_link_type: "confirmed"
    """))
    return p


class TestEndToEndStamping:
    def test_path_a_policy_finding_is_stamped_confirmed(self, policy_file: Path) -> None:
        from sensegnat.policy.engine import PolicyEngine

        svc = SenseGNATService(_FixedAdapter([]))
        svc.policy_engine = PolicyEngine.from_yaml(policy_file)

        # Baseline run
        svc.adapter._events = [_event("host-policy", "10.0.0.1")]
        svc.run_once()

        # Violation run — novel dest outside policy allow-list
        svc.adapter._events = [_event("host-policy", "8.8.8.8")]
        result = svc.run_once()

        policy_indicators = [
            r for r in result
            if r.get("type") == "indicator"
            and r.get("x_gnat_signature") == "policy-violation"
        ]
        assert policy_indicators, "Expected a policy-violation indicator"
        for ind in policy_indicators:
            assert ind["x_gnat_investigation_id"] == "IC-POLICY-001"
            assert ind["x_gnat_investigation_origin"] == "sensegnat"
            assert ind["x_gnat_investigation_link_type"] == "confirmed"

    def test_path_b_hint_finding_is_stamped_inferred(self) -> None:
        svc = SenseGNATService(_FixedAdapter([_event("host-b", "10.0.0.1")]))
        svc._investigation_lookup_enabled = True
        svc.run_once()  # baseline

        svc.adapter._events = [
            _event("host-b", "10.0.0.2", investigation_hint="IC-HINT-002")
        ]
        result = svc.run_once()

        indicators = [r for r in result if r.get("type") == "indicator"]
        assert indicators, "Expected at least one indicator"
        for ind in indicators:
            assert ind["x_gnat_investigation_id"] == "IC-HINT-002"
            assert ind["x_gnat_investigation_link_type"] == "inferred"

    def test_path_c_no_match_finding_has_no_investigation_context(self) -> None:
        svc = SenseGNATService(_FixedAdapter([_event("host-c", "10.0.0.1")]))
        svc._investigation_lookup_enabled = True
        svc.run_once()  # baseline

        svc.adapter._events = [_event("host-c", "10.0.0.2")]  # no hint
        with patch.object(svc.connector, "find_investigations_for_subject", return_value=[]):
            result = svc.run_once()

        indicators = [r for r in result if r.get("type") == "indicator"]
        assert indicators
        for ind in indicators:
            assert "x_gnat_investigation_id" not in ind

    def test_grouping_only_for_tagged_findings(self) -> None:
        svc = SenseGNATService(_FixedAdapter([
            _event("host-b", "10.0.0.1"),
            _event("host-c", "10.0.0.5"),
        ]))
        svc._investigation_lookup_enabled = True
        svc.run_once()  # baseline both subjects

        svc.adapter._events = [
            _event("host-b", "10.0.0.2", investigation_hint="IC-HINT-002"),
            _event("host-c", "10.0.0.6"),  # no hint — path C
        ]
        with patch.object(svc.connector, "find_investigations_for_subject", return_value=[]):
            result = svc.run_once()

        groupings = [r for r in result if r.get("type") == "grouping"]
        assert len(groupings) == 1
        assert groupings[0]["x_gnat_investigation_id"] == "IC-HINT-002"

    def test_existing_tests_still_pass_path_c_default(self) -> None:
        """Smoke-test the no-investigation-context path (95% case)."""
        svc = SenseGNATService(_FixedAdapter([_event("host-x", "10.0.0.1")]))
        first = svc.run_once()
        assert first == []  # no findings on first run (profile just built)

        svc.adapter._events = [_event("host-x", "10.0.0.99")]
        second = svc.run_once()
        indicators = [r for r in second if r.get("type") == "indicator"]
        assert indicators
        assert not any(r.get("type") == "grouping" for r in second)
