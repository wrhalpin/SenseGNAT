from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sensegnat.connectors.gnat_connector import GNATConnector
from sensegnat.models.findings import Finding
from sensegnat.models.narratives import Narrative


def _finding(investigation_id: str | None = None, link_type: str | None = None) -> Finding:
    return Finding(
        finding_id="f1",
        finding_type="rare-destination",
        seen_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        subject_id="alice",
        severity="high",
        score=0.9,
        summary="alice contacted a rare destination",
        evidence={"destination": "198.51.100.1"},
        investigation_id=investigation_id,
        investigation_link_type=link_type,
    )


def _narrative(investigation_id: str | None = None, link_type: str | None = None) -> Narrative:
    return Narrative(
        subject_id="alice",
        finding_count=1,
        finding_types=("rare-destination",),
        severity="high",
        score=0.9,
        summary="alice: 1 finding",
        investigation_id=investigation_id,
        investigation_link_type=link_type,
    )


class TestIndicatorInvestigationStamping:
    def test_investigation_properties_absent_when_no_context(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert "x_gnat_investigation_id" not in stix
        assert "x_gnat_investigation_origin" not in stix
        assert "x_gnat_investigation_link_type" not in stix

    def test_all_three_investigation_properties_stamped(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding("IC-2026-0001", "confirmed"))
        assert stix["x_gnat_investigation_id"] == "IC-2026-0001"
        assert stix["x_gnat_investigation_origin"] == "sensegnat"
        assert stix["x_gnat_investigation_link_type"] == "confirmed"

    def test_link_type_defaults_to_inferred_when_none(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding("IC-2026-0001", None))
        assert stix["x_gnat_investigation_link_type"] == "inferred"

    def test_inferred_link_type_preserved(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding("IC-2026-0001", "inferred"))
        assert stix["x_gnat_investigation_link_type"] == "inferred"


class TestNoteInvestigationStamping:
    def test_investigation_properties_absent_when_no_context(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert "x_gnat_investigation_id" not in stix
        assert "x_gnat_investigation_origin" not in stix
        assert "x_gnat_investigation_link_type" not in stix

    def test_all_three_investigation_properties_stamped(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative("IC-2026-0001", "confirmed"))
        assert stix["x_gnat_investigation_id"] == "IC-2026-0001"
        assert stix["x_gnat_investigation_origin"] == "sensegnat"
        assert stix["x_gnat_investigation_link_type"] == "confirmed"


class TestGrouping:
    def test_grouping_structure(self) -> None:
        conn = GNATConnector()
        g = conn.make_grouping("IC-2026-0001", ["indicator--abc", "note--xyz"], "run-01")
        assert g["type"] == "grouping"
        assert g["spec_version"] == "2.1"
        assert g["context"] == "suspicious-activity"
        assert g["x_gnat_investigation_id"] == "IC-2026-0001"
        assert g["x_gnat_investigation_origin"] == "sensegnat"
        assert set(g["object_refs"]) == {"indicator--abc", "note--xyz"}
        assert "run-01" in g["name"]

    def test_grouping_id_is_unique(self) -> None:
        conn = GNATConnector()
        g1 = conn.make_grouping("IC-001", [], "r1")
        g2 = conn.make_grouping("IC-001", [], "r1")
        assert g1["id"] != g2["id"]
