from __future__ import annotations

from collections import defaultdict

from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent


class ProfileBuilder:
    """Builds a lightweight explainable behavior profile from normalized events."""

    def build(self, events: list[NormalizedNetworkEvent]) -> dict[str, BehaviorProfile]:
        destinations: dict[str, set[str]] = defaultdict(set)
        ports: dict[str, set[int]] = defaultdict(set)
        protocols: dict[str, set[str]] = defaultdict(set)

        for event in events:
            subject_id = event.source_user or event.source_host
            destinations[subject_id].add(event.destination)
            ports[subject_id].add(event.destination_port)
            protocols[subject_id].add(event.protocol.lower())

        profiles: dict[str, BehaviorProfile] = {}
        for subject_id in destinations:
            profiles[subject_id] = BehaviorProfile(
                profile_id=f"profile-{subject_id}",
                subject_id=subject_id,
                common_destinations=frozenset(destinations[subject_id]),
                common_ports=frozenset(ports[subject_id]),
                common_protocols=frozenset(protocols[subject_id]),
            )
        return profiles
