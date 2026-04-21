from __future__ import annotations

from uuid import uuid4

from sensegnat.common.time_utils import utcnow
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.models.findings import Finding


class TimeWindowDriftDetector:
    """Flags subjects whose current-window destination set expands unusually fast.

    Compares the number of novel destinations in this event batch to the size of
    the established profile.  Requires an established profile with at least
    min_profile_size destinations so the ratio is meaningful.

    Args:
        expansion_threshold: fraction of new destinations vs. established that
            triggers a finding (default 0.5 → 50% expansion).
        min_profile_size: minimum established destination count required before
            the detector will fire (default 3).
    """

    def __init__(
        self,
        expansion_threshold: float = 0.5,
        min_profile_size: int = 3,
    ) -> None:
        self._threshold = expansion_threshold
        self._min_profile_size = min_profile_size

    def detect(
        self,
        subject_id: str,
        events: list[NormalizedNetworkEvent],
        profile: BehaviorProfile | None,
    ) -> Finding | None:
        if profile is None or not events:
            return None
        if len(profile.common_destinations) < self._min_profile_size:
            return None

        batch_destinations = {e.destination for e in events}
        novel = batch_destinations - profile.common_destinations
        if not novel:
            return None

        expansion_ratio = len(novel) / len(profile.common_destinations)
        if expansion_ratio < self._threshold:
            return None

        score = min(round(expansion_ratio, 2), 1.0)
        return Finding(
            finding_id=str(uuid4()),
            finding_type="time-window-drift",
            seen_at=utcnow(),
            subject_id=subject_id,
            severity="medium",
            score=score,
            summary=(
                f"{subject_id} contacted {len(novel)} novel destination(s) this window "
                f"({expansion_ratio:.0%} expansion over {len(profile.common_destinations)}-destination profile)"
            ),
            evidence={
                "novel_destination_count": str(len(novel)),
                "established_destination_count": str(len(profile.common_destinations)),
                "expansion_ratio": f"{expansion_ratio:.2f}",
                "expansion_threshold": f"{self._threshold:.2f}",
            },
        )
