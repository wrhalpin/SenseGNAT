from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.models.findings import Finding


class PeerDeviationDetector:
    """Flags behavior that diverges from what peers in the same group have been observed doing."""

    def detect(
        self,
        event: NormalizedNetworkEvent,
        profile: BehaviorProfile | None,
        peer_profiles: list[BehaviorProfile] | None = None,
    ) -> Finding | None:
        if profile is None or not peer_profiles:
            return None

        peer_destinations = frozenset().union(*(p.common_destinations for p in peer_profiles))
        peer_ports = frozenset().union(*(p.common_ports for p in peer_profiles))

        destination_deviation = event.destination not in peer_destinations
        port_deviation = event.destination_port not in peer_ports

        if not destination_deviation and not port_deviation:
            return None

        deviations: list[str] = []
        evidence: dict[str, str] = {
            "peer_group": profile.peer_group or "unknown",
            "peer_count": str(len(peer_profiles)),
        }

        if destination_deviation:
            evidence["destination"] = event.destination
            deviations.append(f"destination {event.destination} not seen by peer group")
        if port_deviation:
            evidence["port"] = str(event.destination_port)
            deviations.append(f"port {event.destination_port} not used by peer group")

        return Finding(
            finding_id=str(uuid4()),
            finding_type="peer-deviation",
            seen_at=datetime.now(timezone.utc),
            subject_id=profile.subject_id,
            severity="medium",
            score=0.70,
            summary=f"{profile.subject_id} deviated from peer group: {'; '.join(deviations)}",
            evidence=evidence,
        )
