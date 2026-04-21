from __future__ import annotations

from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.findings import Finding


class InMemoryProfileStore:
    def __init__(self) -> None:
        self._profiles: dict[str, BehaviorProfile] = {}

    def get(self, subject_id: str) -> BehaviorProfile | None:
        return self._profiles.get(subject_id)

    def put_many(self, profiles: dict[str, BehaviorProfile]) -> None:
        self._profiles.update(profiles)


class InMemoryFindingStore:
    def __init__(self) -> None:
        self._findings: list[Finding] = []

    def add(self, finding: Finding) -> None:
        self._findings.append(finding)

    def list_all(self) -> list[Finding]:
        return list(self._findings)
