from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sensegnat.policy.engine import PolicyEngine


def _engine(yaml_text: str, tmp_path: Path) -> PolicyEngine:
    p = tmp_path / "policy.yaml"
    p.write_text(textwrap.dedent(yaml_text))
    return PolicyEngine.from_yaml(p)


class TestInvestigationIdParsing:
    def test_investigation_id_returned_when_present(self, tmp_path: Path) -> None:
        engine = _engine(
            """
            subjects:
              alice:
                allowed_destinations: ["10.0.0.1"]
                investigation_id: "IC-2026-0001"
            """,
            tmp_path,
        )
        assert engine.investigation_id("alice") == "IC-2026-0001"

    def test_investigation_id_none_when_absent(self, tmp_path: Path) -> None:
        engine = _engine(
            """
            subjects:
              alice:
                allowed_destinations: ["10.0.0.1"]
            """,
            tmp_path,
        )
        assert engine.investigation_id("alice") is None

    def test_investigation_id_none_for_unknown_subject(self, tmp_path: Path) -> None:
        engine = _engine(
            """
            subjects:
              alice:
                investigation_id: "IC-2026-0001"
            """,
            tmp_path,
        )
        assert engine.investigation_id("bob") is None


class TestInvestigationLinkTypeParsing:
    def test_link_type_returned_when_present(self, tmp_path: Path) -> None:
        engine = _engine(
            """
            subjects:
              alice:
                investigation_id: "IC-2026-0001"
                investigation_link_type: "confirmed"
            """,
            tmp_path,
        )
        assert engine.investigation_link_type("alice") == "confirmed"

    def test_link_type_defaults_to_confirmed_when_absent(self, tmp_path: Path) -> None:
        engine = _engine(
            """
            subjects:
              alice:
                investigation_id: "IC-2026-0001"
            """,
            tmp_path,
        )
        assert engine.investigation_link_type("alice") == "confirmed"

    def test_link_type_inferred_explicit(self, tmp_path: Path) -> None:
        engine = _engine(
            """
            subjects:
              alice:
                investigation_id: "IC-2026-0002"
                investigation_link_type: "inferred"
            """,
            tmp_path,
        )
        assert engine.investigation_link_type("alice") == "inferred"

    def test_link_type_for_unknown_subject_defaults_to_confirmed(self, tmp_path: Path) -> None:
        engine = _engine("subjects: {}", tmp_path)
        assert engine.investigation_link_type("nobody") == "confirmed"
