from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sensegnat.detection.policy_violation import PolicyViolationDetector
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.policy.engine import PolicyEngine


def _event(destination: str = "8.8.8.8", port: int = 443) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id="e1",
        seen_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        source_host="host-1",
        source_user="alice",
        destination=destination,
        destination_port=port,
        protocol="tcp",
    )


def _engine_with_investigation(
    subject: str,
    allowed: list[str],
    investigation_id: str | None,
    link_type: str | None,
    tmp_path: Path,
) -> PolicyEngine:
    lines = [
        "subjects:",
        f"  {subject}:",
        f"    allowed_destinations: {allowed!r}",
        "    allowed_ports: [443]",
    ]
    if investigation_id:
        lines.append(f"    investigation_id: {investigation_id!r}")
    if link_type:
        lines.append(f"    investigation_link_type: {link_type!r}")
    p = tmp_path / "policy.yaml"
    p.write_text("\n".join(lines) + "\n")
    return PolicyEngine.from_yaml(p)


class TestPolicyViolationDetectorStamping:
    def test_finding_stamped_with_investigation_id(self, tmp_path: Path) -> None:
        engine = _engine_with_investigation(
            "alice", ["10.0.0.1"], "IC-2026-0001", "confirmed", tmp_path
        )
        finding = PolicyViolationDetector().detect(_event("8.8.8.8"), engine)
        assert finding is not None
        assert finding.investigation_id == "IC-2026-0001"

    def test_finding_link_type_confirmed(self, tmp_path: Path) -> None:
        engine = _engine_with_investigation(
            "alice", ["10.0.0.1"], "IC-2026-0001", "confirmed", tmp_path
        )
        finding = PolicyViolationDetector().detect(_event("8.8.8.8"), engine)
        assert finding is not None
        assert finding.investigation_link_type == "confirmed"

    def test_finding_link_type_defaults_to_confirmed(self, tmp_path: Path) -> None:
        engine = _engine_with_investigation(
            "alice", ["10.0.0.1"], "IC-2026-0001", None, tmp_path
        )
        finding = PolicyViolationDetector().detect(_event("8.8.8.8"), engine)
        assert finding is not None
        assert finding.investigation_link_type == "confirmed"

    def test_no_investigation_context_when_rule_has_none(self, tmp_path: Path) -> None:
        engine = _engine_with_investigation(
            "alice", ["10.0.0.1"], None, None, tmp_path
        )
        finding = PolicyViolationDetector().detect(_event("8.8.8.8"), engine)
        assert finding is not None
        assert finding.investigation_id is None
        assert finding.investigation_link_type is None

    def test_no_finding_when_destination_allowed(self, tmp_path: Path) -> None:
        engine = _engine_with_investigation(
            "alice", ["10.0.0.1"], "IC-2026-0001", "confirmed", tmp_path
        )
        finding = PolicyViolationDetector().detect(_event("10.0.0.1"), engine)
        assert finding is None
