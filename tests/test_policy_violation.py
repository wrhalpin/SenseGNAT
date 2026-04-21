from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sensegnat.detection.policy_violation import PolicyViolationDetector
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.policy.engine import PolicyEngine


_POLICY_YAML = """\
groups:
  engineering:
    members: [alice, bob]
    allowed_destinations:
      - 203.0.113.10
    allowed_ports: [22, 443]

subjects:
  alice:
    peer_group: engineering
    allowed_destinations:
      - 198.51.100.44
    allowed_ports: [8443]

  bob:
    peer_group: engineering
"""


@pytest.fixture
def engine(tmp_path: Path) -> PolicyEngine:
    p = tmp_path / "policies.yaml"
    p.write_text(_POLICY_YAML)
    return PolicyEngine.from_yaml(p)


def _event(
    destination: str = "203.0.113.10",
    port: int = 443,
    source_user: str = "alice",
) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id="e1",
        seen_at=datetime.now(timezone.utc),
        source_host="host-1",
        source_user=source_user,
        destination=destination,
        destination_port=port,
        protocol="tcp",
    )


class TestPolicyViolationDetector:
    def setup_method(self) -> None:
        self.detector = PolicyViolationDetector()

    def test_returns_none_when_no_policy_engine(self) -> None:
        assert self.detector.detect(_event(), policy_engine=None) is None

    def test_no_finding_for_allowed_destination_and_port(self, engine: PolicyEngine) -> None:
        assert self.detector.detect(_event("203.0.113.10", 443), engine) is None

    def test_no_finding_for_subject_direct_destination(self, engine: PolicyEngine) -> None:
        assert self.detector.detect(_event("198.51.100.44", 8443), engine) is None

    def test_flags_destination_not_in_allow_list(self, engine: PolicyEngine) -> None:
        finding = self.detector.detect(_event("10.99.99.99", 443), engine)
        assert finding is not None
        assert finding.finding_type == "policy-violation"
        assert finding.evidence["destination"] == "10.99.99.99"

    def test_flags_port_not_in_allow_list(self, engine: PolicyEngine) -> None:
        finding = self.detector.detect(_event("203.0.113.10", 9999), engine)
        assert finding is not None
        assert finding.finding_type == "policy-violation"
        assert finding.evidence["port"] == "9999"

    def test_flags_both_destination_and_port_violation(self, engine: PolicyEngine) -> None:
        finding = self.detector.detect(_event("10.99.99.99", 9999), engine)
        assert finding is not None
        assert "destination" in finding.evidence
        assert "port" in finding.evidence

    def test_severity_is_high(self, engine: PolicyEngine) -> None:
        finding = self.detector.detect(_event("10.99.99.99", 443), engine)
        assert finding is not None
        assert finding.severity == "high"
        assert finding.score == 0.90

    def test_summary_names_subject(self, engine: PolicyEngine) -> None:
        finding = self.detector.detect(_event("10.99.99.99", 443), engine)
        assert finding is not None
        assert "alice" in finding.summary

    def test_no_finding_when_subject_has_no_policy(self, engine: PolicyEngine) -> None:
        # "charlie" has no entries in the policy — empty allow-list means no rules defined
        event = NormalizedNetworkEvent(
            event_id="e1",
            seen_at=datetime.now(timezone.utc),
            source_host="host-3",
            source_user="charlie",
            destination="10.99.99.99",
            destination_port=9999,
            protocol="tcp",
        )
        assert self.detector.detect(event, engine) is None

    def test_source_host_used_as_subject_when_no_user(self, engine: PolicyEngine) -> None:
        # host with no user — no policy defined for host-1, so no finding
        event = NormalizedNetworkEvent(
            event_id="e1",
            seen_at=datetime.now(timezone.utc),
            source_host="host-1",
            source_user=None,
            destination="10.99.99.99",
            destination_port=9999,
            protocol="tcp",
        )
        assert self.detector.detect(event, engine) is None
