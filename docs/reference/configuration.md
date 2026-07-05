# Configuration Reference

Configuration is managed through Pydantic `BaseModel` classes. The root model is `SenseGNATSettings`. Settings are loaded from a YAML file via `load_settings(path)`.

**Module:** `sensegnat/config/settings.py`

---

## `load_settings`

```python
def load_settings(path: Path) -> SenseGNATSettings
```

Reads the YAML file at `path`, parses it with `yaml.safe_load`, expands environment-variable references, and validates the result against `SenseGNATSettings` using `model_validate`. Raises Pydantic `ValidationError` on schema violations.

### Environment-variable interpolation

Any `${VAR}` reference inside a YAML string value is replaced with the value of that environment variable at load time. Use this to keep secrets out of config files:

```yaml
gnat:
  api_key: "${GNAT_API_KEY}"
adapter:
  type: splunk
  token: "${SPLUNK_TOKEN}"
```

Referencing an **unset** variable raises `ValueError` naming the missing variable — an empty credential is never silently substituted. `$VAR` without braces and `$` in ordinary text are left untouched. Interpolation applies recursively through nested mappings and lists; non-string values are never modified.

---

## `SenseGNATSettings`

Root settings model.

```python
class SenseGNATSettings(BaseModel):
    product_name:  str                     = "SenseGNAT"
    tagline:       str                     = "Behavior is the signal."
    adapter:       AdapterSettings | None  = None
    runtime:       RuntimeSettings         = RuntimeSettings()
    storage:       StorageSettings         = StorageSettings()
    policy_path:   Path | None             = None
    gnat:          GNATSettings            = GNATSettings()
    investigation: InvestigationSettings   = InvestigationSettings()
```

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `product_name` | `str` | `"SenseGNAT"` | Display name for the product. Informational only. |
| `tagline` | `str` | `"Behavior is the signal."` | Product tagline. Informational only. |
| `adapter` | `AdapterSettings \| None` | `None` | Which `EventAdapter` the CLI builds. `None` means the adapter must be constructed in code. |
| `runtime` | `RuntimeSettings` | see below | Runtime behaviour parameters. |
| `storage` | `StorageSettings` | see below | Paths for JSON-backed profile and finding stores. |
| `policy_path` | `Path \| None` | `None` | Path to the YAML policy file. `None` means no policy engine is instantiated. |
| `gnat` | `GNATSettings` | see below | GNAT/TAXII connection parameters. |
| `investigation` | `InvestigationSettings` | see [investigation-context](investigation-context.md) | Path B lookup feature flag and tuning. |

---

## `AdapterSettings`

Selects and parameterizes the `EventAdapter` that `sensegnat run` builds via `build_adapter()` (`sensegnat/ingestion/factory.py`). Only the fields relevant to the chosen `type` are read.

```python
class AdapterSettings(BaseModel):
    type: str = "sample"   # sample | csv | zeek | suricata | gnat_telemetry | splunk
```

| `type` | Required fields | Optional fields |
|---|---|---|
| `sample` | — | — |
| `csv` / `zeek` / `suricata` | `path` | — |
| `gnat_telemetry` | — | `topic` (default `gnat.telemetry`), `brokers`, `group_id`, `max_messages` |
| `splunk` | `spl_query`, `host` | `port` (default 8089), `token`, `username`, `password`, `earliest_time` (default `-24h`), `latest_time` (default `now`), `max_messages` |

Unknown types and missing required fields raise `ValueError` at startup.

```yaml
adapter:
  type: splunk
  spl_query: "search index=network sourcetype=stream:tcp | fields _time, src, dest, dest_port, transport, bytes_in, bytes_out"
  host: splunk.corp
  token: "${SPLUNK_TOKEN}"
```

---

## `RuntimeSettings`

Controls pipeline behaviour at runtime.

```python
class RuntimeSettings(BaseModel):
    environment:          str = "dev"
    lookback_hours:       int = 24
    profile_window_days:  int = 14
```

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `environment` | `str` | `"dev"` | Deployment environment label (e.g., `"dev"`, `"staging"`, `"prod"`). Informational; no behaviour changes based on this value in the current codebase. |
| `lookback_hours` | `int` | `24` | How many hours of historical events to consider in a single pipeline run. Informational; enforced by the caller. |
| `profile_window_days` | `int` | `14` | Number of days over which to accumulate behavioral profiles. Informational; enforced by the caller. |

---

## `StorageSettings`

Controls where JSON-backed stores persist data on disk.

```python
class StorageSettings(BaseModel):
    profile_store_path: Path = Path("./var/profiles.json")
    finding_store_path: Path = Path("./var/findings.json")
```

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `profile_store_path` | `Path` | `Path("./var/profiles.json")` | File path for `JsonProfileStore`. Created on first write if it does not exist. |
| `finding_store_path` | `Path` | `Path("./var/findings.json")` | File path for `JsonFindingStore`. Created on first write if it does not exist. |

### Notes

- Paths are relative to the process working directory when expressed as relative paths in YAML.
- The `./var/` directory must exist before the stores attempt to write. It is not created automatically.

---

## `GNATSettings`

Controls the GNAT TAXII endpoint and all STIX output parameters used by `GNATConnector`.

```python
class GNATSettings(BaseModel):
    base_url:   str = ""
    api_key:    str = ""
    workspace:  str = "gnat"
    tlp:        str = "white"
    confidence: int = 75
    timeout:    int = 30
```

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `base_url` | `str` | `""` | Root URL of the GNAT server, e.g. `"https://gnat.example.com"`. Empty string disables HTTP pushes. |
| `api_key` | `str` | `""` | Bearer token for GNAT API authentication. Empty string disables HTTP pushes. |
| `workspace` | `str` | `"gnat"` | TAXII collection/workspace name. Used in the endpoint path. |
| `tlp` | `str` | `"white"` | TLP marking applied to all STIX objects produced by `GNATConnector`. |
| `confidence` | `int` | `75` | STIX confidence score (0–100) applied to all Indicator objects. |
| `timeout` | `int` | `30` | HTTP request timeout in seconds for TAXII push calls. |

### Notes

- If either `base_url` or `api_key` is empty, `GNATConnector` will log a warning and skip all HTTP pushes. `to_record()` and `narrative_to_record()` still return STIX dicts without making network calls.
- `tlp` is not validated against the TLP vocabulary; any string is accepted.
- `confidence` is not range-validated by Pydantic; values outside 0–100 will be passed through to STIX output.

---

## Complete annotated YAML example

```yaml
# sensegnat.yaml — SenseGNAT configuration file
# Load with: load_settings(Path("sensegnat.yaml"))

product_name: SenseGNAT
tagline: Behavior is the signal.

runtime:
  # Deployment context label — informational only.
  environment: prod

  # Hours of events to consider per run.
  lookback_hours: 24

  # Days over which to accumulate behavioral baselines.
  profile_window_days: 14

storage:
  # JSON file for persisting BehaviorProfile objects between runs.
  # Parent directory must exist.
  profile_store_path: ./var/profiles.json

  # JSON file for persisting Finding objects between runs.
  finding_store_path: ./var/findings.json

# Path to the YAML policy file.
# Omit or set to null to run without a PolicyEngine.
policy_path: ./config/policies.yaml

gnat:
  # Root URL of your GNAT instance. Leave empty to disable HTTP pushes.
  base_url: https://gnat.example.com

  # Bearer token issued by GNAT. Leave empty to disable HTTP pushes.
  api_key: ""

  # TAXII collection name inside GNAT.
  workspace: gnat

  # TLP marking on all emitted STIX objects.
  tlp: white

  # STIX confidence score (0-100).
  confidence: 75

  # HTTP timeout in seconds for TAXII push requests.
  timeout: 30
```

---

## Minimal YAML (all defaults)

```yaml
product_name: SenseGNAT
tagline: Behavior is the signal.
runtime:
  environment: dev
  lookback_hours: 24
  profile_window_days: 14
storage:
  profile_store_path: ./var/profiles.json
  finding_store_path: ./var/findings.json
```

This is equivalent to constructing `SenseGNATSettings()` with no arguments. `policy_path` is `None` and `gnat` uses all defaults.
