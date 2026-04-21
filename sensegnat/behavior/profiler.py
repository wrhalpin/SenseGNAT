from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent

if TYPE_CHECKING:
    from sensegnat.policy.engine import PolicyEngine


class ProfileBuilder:
    """Builds a lightweight explainable behavior profile from normalized events."""

    def build(
        self,
        events: list[NormalizedNetworkEvent],
        policy_engine: PolicyEngine | None = None,
    ) -> dict[str, BehaviorProfile]:
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
            policy_destinations: frozenset[str] = frozenset()
            policy_ports: frozenset[int] = frozenset()
            policy_protocols: frozenset[str] = frozenset()
            peer_group: str | None = None
            if policy_engine is not None:
                policy_destinations = policy_engine.allowed_destinations(subject_id)
                policy_ports = policy_engine.allowed_ports(subject_id)
                policy_protocols = policy_engine.allowed_protocols(subject_id)
                peer_group = policy_engine.peer_group(subject_id)
            profiles[subject_id] = BehaviorProfile(
                profile_id=f"profile-{subject_id}",
                subject_id=subject_id,
                peer_group=peer_group,
                common_destinations=frozenset(destinations[subject_id]) | policy_destinations,
                common_ports=frozenset(ports[subject_id]) | policy_ports,
                common_protocols=frozenset(protocols[subject_id]) | policy_protocols,
            )
        return profiles
