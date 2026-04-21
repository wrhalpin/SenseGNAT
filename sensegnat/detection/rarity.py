from __future__ import annotations

from uuid import uuid4

from sensegnat.common.time_utils import utcnow
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.models.findings import Finding


class RareDestinationDetector:
    """Flags destinations not previously present in a subject profile."""

    def detect(
        self,
        event: NormalizedNetworkEvent,
        profile: BehaviorProfile | None,
    ) -> Finding | None:
        if profile is None:
            return None
        if event.destination in profile.common_destinations:
            return None
        subject_id = event.source_user or event.source_host
        return Finding(
            finding_id=str(uuid4()),
            finding_type="rare-destination",
            seen_at=utcnow(),
            subject_id=subject_id,
            severity="medium",
            score=0.65,
            summary=f"{subject_id} contacted a rare destination {event.destination}",
            evidence={
                "destination": event.destination,
                "port": str(event.destination_port),
                "protocol": event.protocol,
            },
        )
