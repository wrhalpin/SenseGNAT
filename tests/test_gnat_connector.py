from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from sensegnat.connectors.gnat_connector import GNATConnector, PushResult
from sensegnat.models.findings import Finding
from sensegnat.models.narratives import Narrative


_SEEN_AT = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


def _finding(**kwargs) -> Finding:
    defaults = dict(
        finding_id="abc123",
        finding_type="rare-destination",
        seen_at=_SEEN_AT,
        subject_id="alice",
        severity="medium",
        score=0.65,
        summary="alice contacted a rare destination 203.0.113.10",
        evidence={"destination": "203.0.113.10", "port": "443", "protocol": "tcp"},
    )
    defaults.update(kwargs)
    return Finding(**defaults)


def _narrative(**kwargs) -> Narrative:
    defaults = dict(
        subject_id="alice",
        finding_count=2,
        finding_types=("rare-destination", "peer-deviation"),
        severity="medium",
        score=0.70,
        summary="alice: 2 findings (rare-destination ×2)",
    )
    defaults.update(kwargs)
    return Narrative(**defaults)


class TestFindingToStix:
    def test_type_is_indicator(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["type"] == "indicator"

    def test_spec_version(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["spec_version"] == "2.1"

    def test_id_prefixed_indicator(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["id"].startswith("indicator--")

    def test_pattern_uses_destination_ip(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["pattern"] == "[ipv4-addr:value = '203.0.113.10']"

    def test_pattern_falls_back_to_subject_when_no_destination(self) -> None:
        f = _finding(evidence={})
        stix = GNATConnector().finding_to_stix(f)
        assert "x-sensegnat-subject:id = 'alice'" in stix["pattern"]

    def test_name_encodes_type_and_subject(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["name"] == "sensegnat:rare-destination:alice"

    def test_valid_from_is_seen_at(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["valid_from"] == _SEEN_AT.isoformat()

    def test_indicator_types(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["indicator_types"] == ["anomalous-activity"]

    def test_x_gnat_sensor_type_is_ids_alert(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["x_gnat_sensor_type"] == "ids_alert"

    def test_x_gnat_sensor_id_is_sensegnat(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["x_gnat_sensor_id"] == "sensegnat"

    def test_x_gnat_signature_is_finding_type(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["x_gnat_signature"] == "rare-destination"

    def test_x_gnat_tags_contains_subject_id(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert "alice" in stix["x_gnat_tags"]

    def test_x_gnat_tlp_default_white(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["x_gnat_tlp"] == "white"

    def test_x_gnat_tlp_respects_config(self) -> None:
        stix = GNATConnector(tlp="amber").finding_to_stix(_finding())
        assert stix["x_gnat_tlp"] == "amber"

    def test_confidence_default(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["confidence"] == 75

    def test_confidence_configurable(self) -> None:
        stix = GNATConnector(confidence=90).finding_to_stix(_finding())
        assert stix["confidence"] == 90

    def test_sensegnat_score(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["x_sensegnat_score"] == 0.65

    def test_sensegnat_severity(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["x_sensegnat_severity"] == "medium"

    def test_sensegnat_summary(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert "alice" in stix["x_sensegnat_summary"]

    def test_sensegnat_evidence(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["x_sensegnat_evidence"]["port"] == "443"

    def test_sensegnat_finding_id(self) -> None:
        stix = GNATConnector().finding_to_stix(_finding())
        assert stix["x_sensegnat_finding_id"] == "abc123"

    def test_to_record_returns_stix_indicator(self) -> None:
        stix = GNATConnector().to_record(_finding())
        assert stix["type"] == "indicator"
        assert stix["spec_version"] == "2.1"


class TestNarrativeToStix:
    def test_type_is_note(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["type"] == "note"

    def test_spec_version(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["spec_version"] == "2.1"

    def test_id_prefixed_note(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["id"].startswith("note--")

    def test_content_is_summary(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert "alice" in stix["content"]

    def test_object_refs_empty(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["object_refs"] == []

    def test_x_gnat_sensor_id(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["x_gnat_sensor_id"] == "sensegnat"

    def test_subject_id(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["x_sensegnat_subject_id"] == "alice"

    def test_finding_count(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["x_sensegnat_finding_count"] == 2

    def test_finding_types_serialized_as_list(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["x_sensegnat_finding_types"] == ["rare-destination", "peer-deviation"]

    def test_severity(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["x_sensegnat_severity"] == "medium"

    def test_score(self) -> None:
        stix = GNATConnector().narrative_to_stix(_narrative())
        assert stix["x_sensegnat_score"] == 0.70

    def test_narrative_to_record_returns_stix_note(self) -> None:
        stix = GNATConnector().narrative_to_record(_narrative())
        assert stix["type"] == "note"
        assert stix["spec_version"] == "2.1"


class TestPushResult:
    def test_ok_when_no_errors(self) -> None:
        assert PushResult(pushed=3).ok is True

    def test_not_ok_when_errors(self) -> None:
        assert PushResult(errors=["HTTP 500: error"]).ok is False


class TestPushSkippedWhenUnconfigured:
    def test_push_findings_returns_empty_result_without_config(self) -> None:
        result = GNATConnector().push_findings([_finding()])
        assert result.pushed == 0
        assert result.ok is True

    def test_push_narratives_returns_empty_result_without_config(self) -> None:
        result = GNATConnector().push_narratives([_narrative()])
        assert result.pushed == 0
        assert result.ok is True

    def test_push_findings_empty_list_returns_zero(self) -> None:
        result = GNATConnector(base_url="http://x", api_key="k").push_findings([])
        assert result.pushed == 0


class TestBundleShape:
    """Verify the STIX bundle POSTed to GNAT is well-formed."""

    def test_bundle_sent_to_taxii_endpoint(self) -> None:
        captured: list[dict] = []

        def fake_urlopen(req, timeout):  # noqa: ARG001
            body = json.loads(req.data.decode())
            captured.append(body)
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.status = 200
            return mock_resp

        conn = GNATConnector(base_url="https://gnat.example.com", api_key="tok", workspace="main")
        with patch("urllib.request.urlopen", fake_urlopen):
            result = conn.push_findings([_finding()])

        assert result.pushed == 1
        assert result.ok is True
        bundle = captured[0]
        assert bundle["type"] == "bundle"
        assert bundle["spec_version"] == "2.1"
        assert bundle["id"].startswith("bundle--")
        assert len(bundle["objects"]) == 1
        assert bundle["objects"][0]["type"] == "indicator"

    def test_correct_taxii_url_constructed(self) -> None:
        urls: list[str] = []

        def fake_urlopen(req, timeout):  # noqa: ARG001
            urls.append(req.full_url)
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.status = 200
            return mock_resp

        conn = GNATConnector(base_url="https://gnat.example.com", api_key="tok", workspace="main")
        with patch("urllib.request.urlopen", fake_urlopen):
            conn.push_findings([_finding()])

        assert urls[0] == (
            "https://gnat.example.com/taxii2/roots/gnat/collections/main/objects/"
        )

    def test_bearer_auth_header_set(self) -> None:
        headers_sent: list[dict] = []

        def fake_urlopen(req, timeout):  # noqa: ARG001
            headers_sent.append(dict(req.headers))
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.status = 200
            return mock_resp

        conn = GNATConnector(base_url="https://gnat.example.com", api_key="mytoken")
        with patch("urllib.request.urlopen", fake_urlopen):
            conn.push_findings([_finding()])

        auth = headers_sent[0].get("Authorization", "")
        assert auth == "Bearer mytoken"

    def test_http_error_captured_in_result(self) -> None:
        import urllib.error

        def fake_urlopen(req, timeout):  # noqa: ARG001
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

        conn = GNATConnector(base_url="https://gnat.example.com", api_key="bad")
        with patch("urllib.request.urlopen", fake_urlopen):
            result = conn.push_findings([_finding()])

        assert result.pushed == 0
        assert not result.ok
        assert "401" in result.errors[0]

    def test_network_error_captured_in_result(self) -> None:
        def fake_urlopen(req, timeout):  # noqa: ARG001
            raise OSError("connection refused")

        conn = GNATConnector(base_url="https://gnat.example.com", api_key="tok")
        with patch("urllib.request.urlopen", fake_urlopen):
            result = conn.push_findings([_finding()])

        assert not result.ok
        assert "connection refused" in result.errors[0]

    def test_multiple_findings_in_one_bundle(self) -> None:
        captured: list[dict] = []

        def fake_urlopen(req, timeout):  # noqa: ARG001
            captured.append(json.loads(req.data.decode()))
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.status = 200
            return mock_resp

        conn = GNATConnector(base_url="https://gnat.example.com", api_key="tok")
        findings = [_finding(finding_id=f"id{i}", subject_id=f"user{i}") for i in range(3)]
        with patch("urllib.request.urlopen", fake_urlopen):
            result = conn.push_findings(findings)

        assert result.pushed == 3
        assert len(captured[0]["objects"]) == 3
