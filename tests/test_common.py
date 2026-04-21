from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sensegnat.common.serialization import to_dict
from sensegnat.common.time_utils import utcnow
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.findings import Finding


# ── to_dict ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Simple:
    name: str
    value: int


def test_to_dict_basic_dataclass() -> None:
    result = to_dict(_Simple(name="x", value=42))
    assert result == {"name": "x", "value": 42}


def test_to_dict_datetime_to_iso() -> None:
    dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert to_dict(dt) == "2024-06-01T12:00:00+00:00"


def test_to_dict_frozenset_to_sorted_list() -> None:
    assert to_dict(frozenset({3, 1, 2})) == [1, 2, 3]


def test_to_dict_set_to_sorted_list() -> None:
    assert to_dict({"c", "a", "b"}) == ["a", "b", "c"]


def test_to_dict_tuple_to_list() -> None:
    assert to_dict(("x", "y")) == ["x", "y"]


def test_to_dict_list_passthrough() -> None:
    assert to_dict([1, 2, 3]) == [1, 2, 3]


def test_to_dict_dict_recurses_values() -> None:
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = to_dict({"ts": dt, "label": "ok"})
    assert result["ts"] == "2024-01-01T00:00:00+00:00"
    assert result["label"] == "ok"


def test_to_dict_primitives_pass_through() -> None:
    assert to_dict(42) == 42
    assert to_dict(3.14) == 3.14
    assert to_dict("hello") == "hello"
    assert to_dict(None) is None


def test_to_dict_behavior_profile() -> None:
    profile = BehaviorProfile(
        profile_id="p-alice",
        subject_id="alice",
        peer_group="engineering",
        common_destinations=frozenset({"203.0.113.10", "10.0.0.1"}),
        common_ports=frozenset({443, 80}),
        common_protocols=frozenset({"tcp"}),
    )
    result = to_dict(profile)
    assert result["subject_id"] == "alice"
    assert result["peer_group"] == "engineering"
    assert result["common_destinations"] == ["10.0.0.1", "203.0.113.10"]  # sorted
    assert result["common_ports"] == [80, 443]                            # sorted
    assert result["common_protocols"] == ["tcp"]


def test_to_dict_finding_serialises_datetime() -> None:
    finding = Finding(
        finding_id="f-1",
        finding_type="rare-destination",
        seen_at=datetime(2024, 3, 15, 9, 0, 0, tzinfo=timezone.utc),
        subject_id="alice",
        severity="medium",
        score=0.65,
        summary="test",
        evidence={"destination": "1.2.3.4"},
    )
    result = to_dict(finding)
    assert isinstance(result["seen_at"], str)
    assert "2024-03-15" in result["seen_at"]
    assert result["evidence"] == {"destination": "1.2.3.4"}


# ── utcnow ────────────────────────────────────────────────────────────────────

def test_utcnow_returns_datetime() -> None:
    assert isinstance(utcnow(), datetime)


def test_utcnow_is_timezone_aware() -> None:
    assert utcnow().tzinfo is not None


def test_utcnow_is_utc() -> None:
    now = utcnow()
    assert now.utcoffset().total_seconds() == 0


def test_utcnow_is_recent() -> None:
    before = datetime.now(timezone.utc)
    now = utcnow()
    after = datetime.now(timezone.utc)
    assert before <= now <= after
