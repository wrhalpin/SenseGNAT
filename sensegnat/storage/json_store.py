from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sensegnat.common.serialization import to_dict
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.findings import Finding


def _profile_from_dict(d: dict) -> BehaviorProfile:
    return BehaviorProfile(
        profile_id=d["profile_id"],
        subject_id=d["subject_id"],
        peer_group=d.get("peer_group"),
        common_destinations=frozenset(d.get("common_destinations", [])),
        common_ports=frozenset(d.get("common_ports", [])),
        common_protocols=frozenset(d.get("common_protocols", [])),
    )


def _finding_from_dict(d: dict) -> Finding:
    return Finding(
        finding_id=d["finding_id"],
        finding_type=d["finding_type"],
        seen_at=datetime.fromisoformat(d["seen_at"]).replace(tzinfo=timezone.utc),
        subject_id=d["subject_id"],
        severity=d["severity"],
        score=d["score"],
        summary=d["summary"],
        evidence=d["evidence"],
    )


class JsonProfileStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._profiles: dict[str, BehaviorProfile] = {}
        if path.exists():
            self._load()

    def _load(self) -> None:
        data: dict = json.loads(self._path.read_text())
        self._profiles = {k: _profile_from_dict(v) for k, v in data.items()}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({k: to_dict(v) for k, v in self._profiles.items()}, indent=2)
        )

    def get(self, subject_id: str) -> BehaviorProfile | None:
        return self._profiles.get(subject_id)

    def put_many(self, profiles: dict[str, BehaviorProfile]) -> None:
        self._profiles.update(profiles)
        self._save()


class JsonFindingStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._findings: list[Finding] = []
        if path.exists():
            self._load()

    def _load(self) -> None:
        data: list = json.loads(self._path.read_text())
        self._findings = [_finding_from_dict(d) for d in data]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps([to_dict(f) for f in self._findings], indent=2))

    def add(self, finding: Finding) -> None:
        self._findings.append(finding)
        self._save()

    def list_all(self) -> list[Finding]:
        return list(self._findings)
