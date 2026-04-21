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
