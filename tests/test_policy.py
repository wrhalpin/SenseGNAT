from __future__ import annotations

from pathlib import Path

import pytest

from sensegnat.policy.engine import PolicyEngine

_POLICY_YAML = """\
groups:
  engineering:
    members: [alice, bob]
    allowed_destinations:
      - 203.0.113.10
    allowed_ports: [22, 443]
    allowed_protocols: [tcp]

  finance:
    members: [carol]
    allowed_ports: [443]

subjects:
  alice:
    peer_group: engineering
    allowed_destinations:
      - 198.51.100.44
    allowed_ports: [80]

  bob:
    peer_group: engineering

  carol:
    peer_group: finance
"""


@pytest.fixture
def engine(tmp_path: Path) -> PolicyEngine:
    p = tmp_path / "policies.yaml"
    p.write_text(_POLICY_YAML)
    return PolicyEngine.from_yaml(p)


def test_peer_group_lookup(engine: PolicyEngine) -> None:
    assert engine.peer_group("alice") == "engineering"
    assert engine.peer_group("carol") == "finance"
    assert engine.peer_group("nobody") is None


def test_peer_members(engine: PolicyEngine) -> None:
    assert set(engine.peer_members("engineering")) == {"alice", "bob"}
    assert engine.peer_members("finance") == ["carol"]
    assert engine.peer_members("nonexistent") == []


def test_allowed_destinations_merges_subject_and_group(engine: PolicyEngine) -> None:
    destinations = engine.allowed_destinations("alice")
    assert "198.51.100.44" in destinations   # alice-direct
    assert "203.0.113.10" in destinations    # inherited from engineering


def test_allowed_destinations_group_only(engine: PolicyEngine) -> None:
    destinations = engine.allowed_destinations("bob")
    assert "203.0.113.10" in destinations
    assert "198.51.100.44" not in destinations   # alice-only


def test_allowed_ports_merged(engine: PolicyEngine) -> None:
    ports = engine.allowed_ports("alice")
    assert 80 in ports    # alice-direct
    assert 22 in ports    # from engineering
    assert 443 in ports   # from engineering


def test_allowed_protocols(engine: PolicyEngine) -> None:
    assert "tcp" in engine.allowed_protocols("alice")
    assert "tcp" in engine.allowed_protocols("bob")


def test_unknown_subject_returns_empty_sets(engine: PolicyEngine) -> None:
    assert engine.allowed_destinations("ghost") == frozenset()
    assert engine.allowed_ports("ghost") == frozenset()
    assert engine.allowed_protocols("ghost") == frozenset()


def test_empty_rules_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("")
    engine = PolicyEngine.from_yaml(p)
    assert engine.peer_group("alice") is None
    assert engine.allowed_ports("alice") == frozenset()
