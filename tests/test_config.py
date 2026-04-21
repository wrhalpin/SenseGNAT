from __future__ import annotations

from pathlib import Path

import pytest

from sensegnat.config.settings import SenseGNATSettings, load_settings


def test_load_settings_from_yaml(tmp_path: Path) -> None:
    yaml_content = """\
product_name: TestProduct
tagline: Test tagline.
runtime:
  environment: test
  lookback_hours: 48
  profile_window_days: 7
storage:
  profile_store_path: ./var/test_profiles.json
  finding_store_path: ./var/test_findings.json
"""
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(yaml_content)

    settings = load_settings(config_file)

    assert settings.product_name == "TestProduct"
    assert settings.runtime.environment == "test"
    assert settings.runtime.lookback_hours == 48
    assert settings.runtime.profile_window_days == 7
    assert settings.storage.profile_store_path == Path("./var/test_profiles.json")


def test_load_settings_defaults_applied_for_missing_keys(tmp_path: Path) -> None:
    config_file = tmp_path / "minimal.yaml"
    config_file.write_text("product_name: Minimal\n")

    settings = load_settings(config_file)

    assert settings.runtime.environment == "dev"
    assert settings.runtime.lookback_hours == 24
    assert settings.storage.profile_store_path == Path("./var/profiles.json")


def test_sensegnat_settings_defaults() -> None:
    settings = SenseGNATSettings()
    assert settings.product_name == "SenseGNAT"
    assert settings.tagline == "Behavior is the signal."
    assert settings.runtime.lookback_hours == 24
