from __future__ import annotations

from datetime import datetime, timezone

from sensegnat.detection.peer_deviation import PeerDeviationDetector
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent


def _profile(
    subject_id: str,
    peer_group: str = "engineering",
    destinations: list[str] | None = None,
    ports: list[int] | None = None,
) -> BehaviorProfile:
    return BehaviorProfile(
        profile_id=f"profile-{subject_id}",
        subject_id=subject_id,
        peer_group=peer_group,
        common_destinations=frozenset(destinations or ["203.0.113.10"]),
        common_ports=frozenset(ports or [443]),
        common_protocols=frozenset(["tcp"]),
    )


def _event(destination: str = "203.0.113.10", port: int = 443) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id="evt-1",
        seen_at=datetime.now(timezone.utc),
        source_host="host-1",
        source_user="alice",
        destination=destination,
        destination_port=port,
        protocol="tcp",
    )


class TestPeerDeviationDetector:
    def setup_method(self) -> None:
        self.detector = PeerDeviationDetector()

    def test_returns_none_when_no_profile(self) -> None:
        assert self.detector.detect(_event(), None, [_profile("bob")]) is None

    def test_returns_none_when_peer_profiles_is_none(self) -> None:
        assert self.detector.detect(_event(), _profile("alice"), None) is None

    def test_returns_none_when_peer_profiles_is_empty(self) -> None:
        assert self.detector.detect(_event(), _profile("alice"), []) is None

    def test_no_finding_when_event_matches_peer_group(self) -> None:
        alice = _profile("alice", destinations=["203.0.113.10"], ports=[443])
        bob = _profile("bob", destinations=["203.0.113.10"], ports=[443])
        assert self.detector.detect(_event("203.0.113.10", 443), alice, [bob]) is None

    def test_flags_destination_not_seen_by_peers(self) -> None:
        alice = _profile("alice")
        bob = _profile("bob", destinations=["10.0.0.1"])
        finding = self.detector.detect(_event("198.51.100.44", 443), alice, [bob])
        assert finding is not None
        assert finding.finding_type == "peer-deviation"
        assert finding.evidence["destination"] == "198.51.100.44"

    def test_flags_port_not_used_by_peers(self) -> None:
        alice = _profile("alice", ports=[443])
        bob = _profile("bob", ports=[443])
        finding = self.detector.detect(_event("203.0.113.10", 8080), alice, [bob])
        assert finding is not None
        assert finding.evidence["port"] == "8080"

    def test_finding_captures_peer_group_and_count(self) -> None:
        alice = _profile("alice")
        bob = _profile("bob", destinations=["10.0.0.1"])
        charlie = _profile("charlie", destinations=["10.0.0.2"])
        finding = self.detector.detect(_event("198.51.100.44", 443), alice, [bob, charlie])
        assert finding is not None
        assert finding.evidence["peer_group"] == "engineering"
        assert finding.evidence["peer_count"] == "2"

    def test_summary_names_subject_and_mentions_peer_group(self) -> None:
        alice = _profile("alice")
        bob = _profile("bob", destinations=["10.0.0.1"])
        finding = self.detector.detect(_event("198.51.100.44", 443), alice, [bob])
        assert finding is not None
        assert "alice" in finding.summary
        assert "peer group" in finding.summary

    def test_both_destination_and_port_deviation_in_one_finding(self) -> None:
        alice = _profile("alice", destinations=["10.0.0.1"], ports=[22])
        bob = _profile("bob", destinations=["10.0.0.1"], ports=[22])
        finding = self.detector.detect(_event("198.51.100.44", 8080), alice, [bob])
        assert finding is not None
        assert "destination" in finding.evidence
        assert "port" in finding.evidence

    def test_no_finding_when_peer_group_is_none(self) -> None:
        # peer_group=None means no group context — peer deviation should not fire
        alice = BehaviorProfile(
            profile_id="profile-alice",
            subject_id="alice",
            peer_group=None,
            common_destinations=frozenset(["203.0.113.10"]),
            common_ports=frozenset([443]),
            common_protocols=frozenset(["tcp"]),
        )
        bob = _profile("bob", peer_group=None, destinations=["10.0.0.1"])
        # peer_profiles list is non-empty but peer_group is None on alice's profile;
        # the service won't pass peers in this case, so detector receives None
        assert self.detector.detect(_event("198.51.100.44", 443), alice, None) is None
