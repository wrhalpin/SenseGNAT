from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sensegnat.common.time_utils import utcnow
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.models.findings import Finding

if TYPE_CHECKING:
    from sensegnat.policy.engine import PolicyEngine


class PolicyViolationDetector:
    """Flags events that contact destinations or ports outside the subject's policy allow-list.

    Only fires when the policy engine has explicit rules for the subject — an empty
    allow-list means "no policy defined" and is not treated as a violation.
    """

    def detect(
        self,
        event: NormalizedNetworkEvent,
        policy_engine: PolicyEngine | None,
    ) -> Finding | None:
        if policy_engine is None:
            return None

        subject_id = event.source_user or event.source_host
        allowed_destinations = policy_engine.allowed_destinations(subject_id)
        allowed_ports = policy_engine.allowed_ports(subject_id)

        destination_violation = bool(allowed_destinations) and event.destination not in allowed_destinations
        port_violation = bool(allowed_ports) and event.destination_port not in allowed_ports

        if not destination_violation and not port_violation:
            return None

        violations: list[str] = []
        evidence: dict[str, str] = {}

        if destination_violation:
            evidence["destination"] = event.destination
            violations.append(f"destination {event.destination} not in policy allow-list")
        if port_violation:
            evidence["port"] = str(event.destination_port)
            violations.append(f"port {event.destination_port} not in policy allow-list")

        inv_id = policy_engine.investigation_id(subject_id)
        return Finding(
            finding_id=str(uuid4()),
            finding_type="policy-violation",
            seen_at=utcnow(),
            subject_id=subject_id,
            severity="high",
            score=0.90,
            summary=f"{subject_id} policy violation: {'; '.join(violations)}",
            evidence=evidence,
            investigation_id=inv_id,
            investigation_link_type=policy_engine.investigation_link_type(subject_id) if inv_id else None,
        )
