from __future__ import annotations

from pathlib import Path

import yaml


class PolicyEngine:
    """Loads per-subject and per-group policy rules and exposes them to the profiler and detectors."""

    def __init__(self, rules: dict) -> None:
        self._groups: dict[str, dict] = rules.get("groups", {})
        self._subjects: dict[str, dict] = rules.get("subjects", {})

    @classmethod
    def from_yaml(cls, path: Path) -> PolicyEngine:
        raw = yaml.safe_load(path.read_text())
        return cls(raw or {})

    def peer_group(self, subject_id: str) -> str | None:
        return self._subjects.get(subject_id, {}).get("peer_group")

    def peer_members(self, group: str) -> list[str]:
        return list(self._groups.get(group, {}).get("members", []))

    def allowed_destinations(self, subject_id: str) -> frozenset[str]:
        return self._resolve(subject_id, "allowed_destinations", str)

    def allowed_ports(self, subject_id: str) -> frozenset[int]:
        return self._resolve(subject_id, "allowed_ports", int)

    def allowed_protocols(self, subject_id: str) -> frozenset[str]:
        return self._resolve(subject_id, "allowed_protocols", str)

    def _resolve(self, subject_id: str, key: str, cast: type) -> frozenset:
        subject_rules = self._subjects.get(subject_id, {})
        values: set = {cast(v) for v in subject_rules.get(key, [])}
        group = subject_rules.get("peer_group")
        if group:
            values |= {cast(v) for v in self._groups.get(group, {}).get(key, [])}
        return frozenset(values)
