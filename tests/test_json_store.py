from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.findings import Finding
from sensegnat.storage.json_store import JsonFindingStore, JsonProfileStore


def _sample_profile(subject_id: str = "alice") -> BehaviorProfile:
    return BehaviorProfile(
        profile_id=f"profile-{subject_id}",
        subject_id=subject_id,
        common_destinations=frozenset({"203.0.113.10", "10.0.0.1"}),
        common_ports=frozenset({443, 80}),
        common_protocols=frozenset({"tcp"}),
    )


def _sample_finding(subject_id: str = "alice") -> Finding:
    return Finding(
        finding_id="find-001",
        finding_type="rare-destination",
        seen_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        subject_id=subject_id,
        severity="medium",
        score=0.65,
        summary=f"{subject_id} contacted a rare destination",
        evidence={"destination": "198.51.100.44", "port": "443", "protocol": "tcp"},
    )


class TestJsonProfileStore:
    def test_put_and_get(self, tmp_path: Path) -> None:
        store = JsonProfileStore(tmp_path / "profiles.json")
        profile = _sample_profile()
        store.put_many({"alice": profile})

        result = store.get("alice")
        assert result is not None
        assert result.subject_id == "alice"
        assert result.common_destinations == frozenset({"203.0.113.10", "10.0.0.1"})
        assert result.common_ports == frozenset({443, 80})

    def test_get_returns_none_for_missing(self, tmp_path: Path) -> None:
        store = JsonProfileStore(tmp_path / "profiles.json")
        assert store.get("nobody") is None

    def test_persists_to_disk_and_reloads(self, tmp_path: Path) -> None:
        path = tmp_path / "profiles.json"
        store = JsonProfileStore(path)
        store.put_many({"alice": _sample_profile("alice"), "bob": _sample_profile("bob")})

        assert path.exists()

        reloaded = JsonProfileStore(path)
        assert reloaded.get("alice") is not None
        assert reloaded.get("bob") is not None
        assert reloaded.get("alice").common_destinations == frozenset({"203.0.113.10", "10.0.0.1"})

    def test_put_many_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deep" / "profiles.json"
        store = JsonProfileStore(path)
        store.put_many({"alice": _sample_profile()})
        assert path.exists()

    def test_peer_group_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "profiles.json"
        profile = BehaviorProfile(
            profile_id="profile-alice",
            subject_id="alice",
            peer_group="engineering",
            common_destinations=frozenset(),
            common_ports=frozenset(),
            common_protocols=frozenset(),
        )
        store = JsonProfileStore(path)
        store.put_many({"alice": profile})

        reloaded = JsonProfileStore(path)
        assert reloaded.get("alice").peer_group == "engineering"


class TestJsonFindingStore:
    def test_add_and_list_all(self, tmp_path: Path) -> None:
        store = JsonFindingStore(tmp_path / "findings.json")
        finding = _sample_finding()
        store.add(finding)

        results = store.list_all()
        assert len(results) == 1
        assert results[0].finding_id == "find-001"

    def test_persists_to_disk_and_reloads(self, tmp_path: Path) -> None:
        path = tmp_path / "findings.json"
        store = JsonFindingStore(path)
        store.add(_sample_finding())

        assert path.exists()

        reloaded = JsonFindingStore(path)
        results = reloaded.list_all()
        assert len(results) == 1
        assert results[0].finding_type == "rare-destination"
        assert results[0].seen_at == datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_evidence_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "findings.json"
        store = JsonFindingStore(path)
        store.add(_sample_finding())

        reloaded = JsonFindingStore(path)
        assert reloaded.list_all()[0].evidence == {
            "destination": "198.51.100.44",
            "port": "443",
            "protocol": "tcp",
        }

    def test_accumulates_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "findings.json"
        JsonFindingStore(path).add(_sample_finding("alice"))
        JsonFindingStore(path).add(_sample_finding("bob"))

        results = JsonFindingStore(path).list_all()
        assert len(results) == 2
