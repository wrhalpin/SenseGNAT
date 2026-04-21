from datetime import datetime, timezone

from sensegnat.detection.rarity import RareDestinationDetector
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent


def test_rare_destination_detector_flags_unknown_destination() -> None:
    detector = RareDestinationDetector()
    profile = BehaviorProfile(
        profile_id="profile-alice",
        subject_id="alice",
        common_destinations=frozenset({"203.0.113.10"}),
        common_ports=frozenset({443}),
        common_protocols=frozenset({"tcp"}),
    )
    event = NormalizedNetworkEvent(
        event_id="evt-2",
        seen_at=datetime.now(timezone.utc),
        source_host="host-1",
        source_user="alice",
        destination="198.51.100.44",
        destination_port=443,
        protocol="tcp",
    )

    finding = detector.detect(event, profile)
    assert finding is not None
    assert finding.finding_type == "rare-destination"
