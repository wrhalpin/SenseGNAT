from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AdapterSettings(BaseModel):
    """Which EventAdapter to build and its constructor parameters.

    ``type`` selects the adapter; only the fields relevant to that type
    are read (see sensegnat/ingestion/factory.py).
    """

    type: str = "sample"  # sample | csv | zeek | suricata | gnat_telemetry | splunk
    # csv / zeek / suricata
    path: Path | None = None
    # gnat_telemetry (Kafka)
    topic: str = "gnat.telemetry"
    brokers: list[str] | None = None
    group_id: str = "sensegnat"
    max_messages: int | None = None
    # splunk
    spl_query: str | None = None
    host: str | None = None
    port: int = 8089
    token: str | None = None
    username: str | None = None
    password: str | None = None
    earliest_time: str = "-24h"
    latest_time: str = "now"


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
    adapter: AdapterSettings | None = None
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    policy_path: Path | None = None
    gnat: GNATSettings = Field(default_factory=GNATSettings)
    investigation: InvestigationSettings = Field(default_factory=InvestigationSettings)


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(value: object) -> object:
    """Recursively expand ``${VAR}`` references in string values.

    A reference to an unset environment variable is an error — silently
    substituting an empty string would send blank credentials downstream.
    """
    if isinstance(value, str):
        def _sub(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ValueError(
                    f"config references environment variable '{name}' which is not set"
                )
            return os.environ[name]

        return _ENV_VAR_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_settings(path: Path) -> SenseGNATSettings:
    raw = yaml.safe_load(path.read_text())
    return SenseGNATSettings.model_validate(_expand_env(raw))
