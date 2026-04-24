from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from sensegnat.connectors.gnat_connector import GNATConnector


def _conn(ttl: int = 60) -> GNATConnector:
    return GNATConnector(
        base_url="https://gnat.example.com",
        api_key="test-key",
        investigation_lookup_cache_ttl_s=ttl,
    )


def _mock_response(ids: list[str]):
    body = json.dumps({"investigations": [{"investigation_id": i} for i in ids]}).encode()
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.read = MagicMock(return_value=body)
    return mock


class TestFindInvestigationsForSubject:
    def test_returns_ids_on_success(self) -> None:
        conn = _conn()
        with patch("urllib.request.urlopen", return_value=_mock_response(["IC-001", "IC-002"])):
            result = conn.find_investigations_for_subject("alice")
        assert result == ["IC-001", "IC-002"]

    def test_returns_empty_on_timeout(self) -> None:
        conn = _conn()
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = conn.find_investigations_for_subject("alice")
        assert result == []

    def test_returns_empty_on_network_error(self) -> None:
        conn = _conn()
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = conn.find_investigations_for_subject("alice")
        assert result == []

    def test_returns_empty_when_no_credentials(self) -> None:
        conn = GNATConnector()  # no base_url / api_key
        result = conn.find_investigations_for_subject("alice")
        assert result == []

    def test_cache_hit_skips_second_network_call(self) -> None:
        conn = _conn(ttl=60)
        with patch("urllib.request.urlopen", return_value=_mock_response(["IC-001"])) as mock_open:
            conn.find_investigations_for_subject("alice")
            conn.find_investigations_for_subject("alice")
        assert mock_open.call_count == 1

    def test_cache_miss_after_ttl_expires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        conn = _conn(ttl=1)
        t = [0.0]
        monkeypatch.setattr(time, "monotonic", lambda: t[0])

        with patch("urllib.request.urlopen", return_value=_mock_response(["IC-001"])) as mock_open:
            conn.find_investigations_for_subject("alice")
            t[0] = 2.0  # advance past TTL
            conn.find_investigations_for_subject("alice")
        assert mock_open.call_count == 2

    def test_empty_result_is_cached(self) -> None:
        conn = _conn(ttl=60)
        with patch("urllib.request.urlopen", return_value=_mock_response([])) as mock_open:
            conn.find_investigations_for_subject("alice")
            conn.find_investigations_for_subject("alice")
        assert mock_open.call_count == 1

    def test_subject_url_includes_encoded_ref(self) -> None:
        conn = _conn()
        captured_url = []

        def fake_open(req, timeout):
            captured_url.append(req.full_url)
            return _mock_response([])

        with patch("urllib.request.urlopen", side_effect=fake_open):
            conn.find_investigations_for_subject("user@example.com")

        assert "user%40example.com" in captured_url[0]
