from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sensegnat.detection.time_window_drift import TimeWindowDriftDetector
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent


def _profile(destinations: list[str], subject_id: str = "alice") -> BehaviorProfile:
    return BehaviorProfile(
        profile_id=f"profile-{subject_id}",
        subject_id=subject_id,
        common_destinations=frozenset(destinations),
        common_ports=frozenset([443]),
        common_protocols=frozenset(["tcp"]),
    )


def _event(destination: str, subject_id: str = "alice") -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id="e1",
        seen_at=datetime.now(timezone.utc),
        source_host="host-1",
        source_user=subject_id,
        destination=destination,
        destination_port=443,
        protocol="tcp",
    )


class TestTimeWindowDriftDetector:
    def setup_method(self) -> None:
        self.detector = TimeWindowDriftDetector(expansion_threshold=0.5, min_profile_size=3)

    def test_returns_none_when_no_profile(self) -> None:
        events = [_event("10.0.0.1")]
        assert self.detector.detect("alice", events, None) is None

    def test_returns_none_when_no_events(self) -> None:
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        assert self.detector.detect("alice", [], profile) is None

    def test_returns_none_when_profile_too_small(self) -> None:
        # profile has only 2 destinations — below min_profile_size=3
        profile = _profile(["10.0.0.1", "10.0.0.2"])
        events = [_event("10.99.0.1"), _event("10.99.0.2"), _event("10.99.0.3")]
        assert self.detector.detect("alice", events, profile) is None

    def test_returns_none_when_all_destinations_known(self) -> None:
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        events = [_event("10.0.0.1"), _event("10.0.0.2")]
        assert self.detector.detect("alice", events, profile) is None

    def test_returns_none_below_threshold(self) -> None:
        # profile has 4 destinations; 1 novel = 25% expansion — below 50% threshold
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"])
        events = [_event("10.99.0.1")]  # 1 novel / 4 established = 0.25
        assert self.detector.detect("alice", events, profile) is None

    def test_fires_at_threshold(self) -> None:
        # profile has 4 destinations; 2 novel = 50% expansion — at threshold
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"])
        events = [_event("10.99.0.1"), _event("10.99.0.2")]  # 2/4 = 0.50
        finding = self.detector.detect("alice", events, profile)
        assert finding is not None
        assert finding.finding_type == "time-window-drift"

    def test_fires_above_threshold(self) -> None:
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        events = [_event("10.99.0.1"), _event("10.99.0.2"), _event("10.99.0.3")]
        finding = self.detector.detect("alice", events, profile)
        assert finding is not None

    def test_evidence_contains_counts_and_ratio(self) -> None:
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        events = [_event("10.99.0.1"), _event("10.99.0.2")]  # 2/3 ≈ 0.67
        finding = self.detector.detect("alice", events, profile)
        assert finding is not None
        assert finding.evidence["novel_destination_count"] == "2"
        assert finding.evidence["established_destination_count"] == "3"
        assert "expansion_ratio" in finding.evidence
        assert finding.evidence["expansion_threshold"] == "0.50"

    def test_subject_id_in_summary(self) -> None:
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        events = [_event("10.99.0.1"), _event("10.99.0.2")]
        finding = self.detector.detect("alice", events, profile)
        assert finding is not None
        assert "alice" in finding.summary

    def test_score_capped_at_one(self) -> None:
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        # 10 novel destinations — 333% expansion
        events = [_event(f"10.99.0.{i}") for i in range(10)]
        finding = self.detector.detect("alice", events, profile)
        assert finding is not None
        assert finding.score <= 1.0

    def test_duplicate_destinations_counted_once(self) -> None:
        # same novel destination repeated across events — should count as 1 novel dest
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"])
        events = [_event("10.99.0.1")] * 5  # repeated — still only 1 unique novel dest = 0.25
        assert self.detector.detect("alice", events, profile) is None

    def test_custom_threshold(self) -> None:
        detector = TimeWindowDriftDetector(expansion_threshold=0.25, min_profile_size=3)
        profile = _profile(["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"])
        events = [_event("10.99.0.1")]  # 1/4 = 0.25 — fires at lower threshold
        assert detector.detect("alice", events, profile) is not None
