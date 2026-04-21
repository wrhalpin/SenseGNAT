from __future__ import annotations

from pathlib import Path

import pytest

from sensegnat.models.entities import BehaviorProfile
from sensegnat.storage.json_store import JsonProfileStore
from sensegnat.storage.memory import InMemoryProfileStore


def _profile(
    subject_id: str,
    destinations: list[str],
    ports: list[int],
    protocols: list[str] | None = None,
    peer_group: str | None = "engineering",
) -> BehaviorProfile:
    return BehaviorProfile(
        profile_id=f"profile-{subject_id}",
        subject_id=subject_id,
        peer_group=peer_group,
        common_destinations=frozenset(destinations),
        common_ports=frozenset(ports),
        common_protocols=frozenset(protocols or ["tcp"]),
    )


# ── BehaviorProfile.merge() ───────────────────────────────────────────────────

class TestBehaviorProfileMerge:
    def test_destinations_are_unioned(self) -> None:
        a = _profile("alice", destinations=["10.0.0.1"], ports=[443])
        b = _profile("alice", destinations=["10.0.0.2"], ports=[443])
        merged = a.merge(b)
        assert merged.common_destinations == frozenset({"10.0.0.1", "10.0.0.2"})

    def test_ports_are_unioned(self) -> None:
        a = _profile("alice", destinations=["10.0.0.1"], ports=[443])
        b = _profile("alice", destinations=["10.0.0.1"], ports=[80])
        merged = a.merge(b)
        assert merged.common_ports == frozenset({443, 80})

    def test_protocols_are_unioned(self) -> None:
        a = _profile("alice", destinations=["10.0.0.1"], ports=[443], protocols=["tcp"])
        b = _profile("alice", destinations=["10.0.0.1"], ports=[53], protocols=["udp"])
        merged = a.merge(b)
        assert merged.common_protocols == frozenset({"tcp", "udp"})

    def test_incoming_peer_group_takes_precedence(self) -> None:
        a = _profile("alice", destinations=[], ports=[], peer_group="old-group")
        b = _profile("alice", destinations=[], ports=[], peer_group="engineering")
        assert a.merge(b).peer_group == "engineering"

    def test_profile_id_and_subject_id_preserved_from_existing(self) -> None:
        a = _profile("alice", destinations=["10.0.0.1"], ports=[443])
        b = _profile("alice", destinations=["10.0.0.2"], ports=[80])
        merged = a.merge(b)
        assert merged.profile_id == "profile-alice"
        assert merged.subject_id == "alice"

    def test_merge_with_empty_incoming_is_identity(self) -> None:
        a = _profile("alice", destinations=["10.0.0.1"], ports=[443])
        b = _profile("alice", destinations=[], ports=[])
        merged = a.merge(b)
        assert merged.common_destinations == frozenset({"10.0.0.1"})
        assert merged.common_ports == frozenset({443})

    def test_merge_is_not_symmetric_for_peer_group(self) -> None:
        a = _profile("alice", destinations=[], ports=[], peer_group="group-a")
        b = _profile("alice", destinations=[], ports=[], peer_group="group-b")
        assert a.merge(b).peer_group == "group-b"
        assert b.merge(a).peer_group == "group-a"


# ── InMemoryProfileStore.put_many() ──────────────────────────────────────────

class TestInMemoryProfileStoreMerge:
    def test_second_put_merges_destinations(self) -> None:
        store = InMemoryProfileStore()
        store.put_many({"alice": _profile("alice", destinations=["10.0.0.1"], ports=[443])})
        store.put_many({"alice": _profile("alice", destinations=["10.0.0.2"], ports=[80])})
        result = store.get("alice")
        assert result is not None
        assert result.common_destinations == frozenset({"10.0.0.1", "10.0.0.2"})
        assert result.common_ports == frozenset({443, 80})

    def test_new_subject_stored_directly(self) -> None:
        store = InMemoryProfileStore()
        store.put_many({"alice": _profile("alice", destinations=["10.0.0.1"], ports=[443])})
        store.put_many({"bob": _profile("bob", destinations=["10.0.0.2"], ports=[22])})
        assert store.get("alice") is not None
        assert store.get("bob") is not None

    def test_three_runs_accumulate(self) -> None:
        store = InMemoryProfileStore()
        for dest in ["10.0.0.1", "10.0.0.2", "10.0.0.3"]:
            store.put_many({"alice": _profile("alice", destinations=[dest], ports=[443])})
        result = store.get("alice")
        assert result.common_destinations == frozenset({"10.0.0.1", "10.0.0.2", "10.0.0.3"})


# ── JsonProfileStore.put_many() ───────────────────────────────────────────────

class TestJsonProfileStoreMerge:
    def test_second_put_merges_and_persists(self, tmp_path: Path) -> None:
        path = tmp_path / "profiles.json"
        JsonProfileStore(path).put_many(
            {"alice": _profile("alice", destinations=["10.0.0.1"], ports=[443])}
        )
        JsonProfileStore(path).put_many(
            {"alice": _profile("alice", destinations=["10.0.0.2"], ports=[80])}
        )
        result = JsonProfileStore(path).get("alice")
        assert result is not None
        assert result.common_destinations == frozenset({"10.0.0.1", "10.0.0.2"})
        assert result.common_ports == frozenset({443, 80})

    def test_merge_survives_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "profiles.json"
        store = JsonProfileStore(path)
        store.put_many({"alice": _profile("alice", destinations=["10.0.0.1"], ports=[443])})
        store.put_many({"alice": _profile("alice", destinations=["10.0.0.2"], ports=[80])})

        reloaded = JsonProfileStore(path)
        result = reloaded.get("alice")
        assert result.common_destinations == frozenset({"10.0.0.1", "10.0.0.2"})
