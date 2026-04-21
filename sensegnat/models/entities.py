from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet


@dataclass(frozen=True)
class NetworkEntity:
    entity_id: str
    entity_type: str
    display_name: str
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BehaviorProfile:
    profile_id: str
    subject_id: str
    peer_group: str | None = None
    common_destinations: FrozenSet[str] = frozenset()
    common_ports: FrozenSet[int] = frozenset()
    common_protocols: FrozenSet[str] = frozenset()

    def merge(self, incoming: BehaviorProfile) -> BehaviorProfile:
        """Return a new profile that unions observation sets from self and incoming.

        peer_group from incoming takes precedence so policy updates propagate.
        """
        return BehaviorProfile(
            profile_id=self.profile_id,
            subject_id=self.subject_id,
            peer_group=incoming.peer_group,
            common_destinations=self.common_destinations | incoming.common_destinations,
            common_ports=self.common_ports | incoming.common_ports,
            common_protocols=self.common_protocols | incoming.common_protocols,
        )
