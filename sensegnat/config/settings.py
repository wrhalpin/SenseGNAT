from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class StorageSettings(BaseModel):
    profile_store_path: Path = Field(default=Path("./var/profiles.json"))
    finding_store_path: Path = Field(default=Path("./var/findings.json"))


class RuntimeSettings(BaseModel):
    environment: str = "dev"
    lookback_hours: int = 24
    profile_window_days: int = 14


class InvestigationSettings(BaseModel):
    lookup_enabled: bool = False
    lookup_timeout_s: float = 2.0
    lookup_cache_ttl_s: int = 60
    lookup_max_matches: int = 3


class GNATSettings(BaseModel):
    base_url: str = ""
    api_key: str = ""
    workspace: str = "gnat"
    tlp: str = "white"
    confidence: int = 75
    timeout: int = 30


class SenseGNATSettings(BaseModel):
    product_name: str = "SenseGNAT"
    tagline: str = "Behavior is the signal."
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    policy_path: Path | None = None
    gnat: GNATSettings = Field(default_factory=GNATSettings)
    investigation: InvestigationSettings = Field(default_factory=InvestigationSettings)


def load_settings(path: Path) -> SenseGNATSettings:
    raw = yaml.safe_load(path.read_text())
    return SenseGNATSettings.model_validate(raw)
