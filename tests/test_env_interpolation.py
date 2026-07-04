from __future__ import annotations

from pathlib import Path

import pytest

from sensegnat.config.settings import load_settings


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class TestEnvInterpolation:
    def test_env_var_expanded(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("GNAT_API_KEY", "sekrit-token")
        path = _write_config(tmp_path, 'gnat:\n  api_key: "${GNAT_API_KEY}"\n')

        settings = load_settings(path)
        assert settings.gnat.api_key == "sekrit-token"

    def test_env_var_inside_larger_string(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("GNAT_HOST", "gnat.corp")
        path = _write_config(tmp_path, 'gnat:\n  base_url: "https://${GNAT_HOST}:8443"\n')

        settings = load_settings(path)
        assert settings.gnat.base_url == "https://gnat.corp:8443"

    def test_missing_env_var_raises_with_name(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("DEFINITELY_NOT_SET_ANYWHERE", raising=False)
        path = _write_config(
            tmp_path, 'gnat:\n  api_key: "${DEFINITELY_NOT_SET_ANYWHERE}"\n'
        )

        with pytest.raises(ValueError, match="DEFINITELY_NOT_SET_ANYWHERE"):
            load_settings(path)

    def test_plain_strings_untouched(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, "product_name: SenseGNAT\n")
        settings = load_settings(path)
        assert settings.product_name == "SenseGNAT"

    def test_dollar_without_braces_untouched(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, 'tagline: "costs $5 to run"\n')
        settings = load_settings(path)
        assert settings.tagline == "costs $5 to run"

    def test_expansion_inside_lists(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("KAFKA_BROKER", "kafka.corp:9092")
        path = _write_config(
            tmp_path,
            'adapter:\n  type: gnat_telemetry\n  brokers: ["${KAFKA_BROKER}"]\n',
        )

        settings = load_settings(path)
        assert settings.adapter is not None
        assert settings.adapter.brokers == ["kafka.corp:9092"]

    def test_non_string_values_untouched(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, "runtime:\n  lookback_hours: 48\n")
        settings = load_settings(path)
        assert settings.runtime.lookback_hours == 48
