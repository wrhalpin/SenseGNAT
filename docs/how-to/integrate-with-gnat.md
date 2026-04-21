# How to integrate with GNAT

This guide shows you how to push SenseGNAT findings and narratives into a
running GNAT instance using `GNATConnector`.

---

## How the connector works

`GNATConnector` converts `Finding` objects to STIX 2.1 Indicator objects and
`Narrative` objects to STIX 2.1 Notes, then POSTs them as a STIX bundle to
the GNAT TAXII 2.1 collection endpoint:

```
POST /taxii2/roots/gnat/collections/{workspace}/objects/
```

When `base_url` and `api_key` are not set, the connector operates in
**record-only mode**: `to_record()` and `narrative_to_record()` return STIX
dicts without making any network calls. This is the default when you construct
`SenseGNATService` without a settings object.

---

## Minimal push

```python
from sensegnat.connectors.gnat_connector import GNATConnector

connector = GNATConnector(
    base_url="https://gnat.example.com",
    api_key="your-bearer-token",
)

result = connector.push_findings(findings)
if not result.ok:
    print("Push failed:", result.errors)
else:
    print(f"Pushed {result.pushed} finding(s)")
```

`push_findings` accepts a `list[Finding]` and sends all of them in a single
STIX bundle. `push_narratives` works the same way for `list[Narrative]`.

---

## Constructor parameters

```python
GNATConnector(
    base_url="https://gnat.example.com",  # root URL, no trailing slash
    api_key="your-bearer-token",          # Bearer token issued by GNAT
    workspace="gnat",                     # TAXII collection / workspace name
    tlp="white",                          # TLP marking on all STIX objects
    confidence=75,                        # STIX confidence score, 0–100
    timeout=30,                           # HTTP request timeout, seconds
)
```

All parameters have defaults. `base_url` and `api_key` default to `""`,
which enables record-only mode.

---

## Loading config from YAML

Add a `gnat` section to your `sensegnat.yaml`:

```yaml
product_name: SenseGNAT
tagline: Behavior is the signal.

runtime:
  environment: production
  lookback_hours: 24

storage:
  profile_store_path: ./var/profiles.json
  finding_store_path: ./var/findings.json

policy_path: ./policies.yaml

gnat:
  base_url: https://gnat.example.com
  api_key: your-bearer-token
  workspace: sensegnat
  tlp: amber
  confidence: 80
  timeout: 30
```

Then instantiate the service from settings. `SenseGNATService` does not yet
auto-configure the connector from settings — do it directly:

```python
from pathlib import Path
from sensegnat.api.service import SenseGNATService
from sensegnat.config.settings import load_settings
from sensegnat.connectors.gnat_connector import GNATConnector
from sensegnat.ingestion.csv_adapter import CsvEventAdapter

settings = load_settings(Path("sensegnat.yaml"))

service = SenseGNATService(
    adapter=CsvEventAdapter(Path("events.csv")),
    settings=settings,
)

# Replace the default record-only connector with a live one
service.connector = GNATConnector(
    base_url=settings.gnat.base_url,
    api_key=settings.gnat.api_key,
    workspace=settings.gnat.workspace,
    tlp=settings.gnat.tlp,
    confidence=settings.gnat.confidence,
    timeout=settings.gnat.timeout,
)

service.run_once()
```

---

## What a pushed STIX Indicator looks like

The connector calls `finding_to_stix(finding)` for each `Finding`. Below is a
complete example of the resulting object, as it appears inside the STIX bundle
POSTed to GNAT:

```json
{
  "type": "indicator",
  "spec_version": "2.1",
  "id": "indicator--a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created": "2026-04-21T14:30:00.000000+00:00",
  "modified": "2026-04-21T14:30:00.000000+00:00",
  "name": "sensegnat:rare-destination:alice",
  "pattern": "[ipv4-addr:value = '198.51.100.44']",
  "pattern_type": "stix",
  "valid_from": "2026-04-21T14:29:58.123456+00:00",
  "indicator_types": ["anomalous-activity"],
  "confidence": 75,
  "x_gnat_sensor_type": "ids_alert",
  "x_gnat_sensor_id": "sensegnat",
  "x_gnat_signature": "rare-destination",
  "x_gnat_tags": ["alice"],
  "x_gnat_tlp": "white",
  "x_sensegnat_finding_id": "f8e7d6c5-b4a3-2190-fedc-ba0987654321",
  "x_sensegnat_score": 0.65,
  "x_sensegnat_severity": "medium",
  "x_sensegnat_summary": "alice contacted a rare destination 198.51.100.44",
  "x_sensegnat_evidence": {
    "destination": "198.51.100.44",
    "port": "443",
    "protocol": "tcp"
  },
  "x_sensegnat_subject_id": "alice"
}
```

When the `evidence` dict does not contain a `"destination"` key, the `pattern`
falls back to:

```json
"pattern": "[x-sensegnat-subject:id = 'alice']"
```

The STIX bundle wrapper that GNAT receives looks like:

```json
{
  "type": "bundle",
  "id": "bundle--...",
  "spec_version": "2.1",
  "objects": [ ... one indicator per finding ... ]
}
```

---

## What a pushed STIX Note (Narrative) looks like

```json
{
  "type": "note",
  "spec_version": "2.1",
  "id": "note--c1d2e3f4-a5b6-7890-cdef-012345678901",
  "created": "2026-04-21T14:30:01.000000+00:00",
  "modified": "2026-04-21T14:30:01.000000+00:00",
  "content": "alice: 2 findings (rare-destination x2)",
  "object_refs": [],
  "x_gnat_sensor_id": "sensegnat",
  "x_gnat_tlp": "white",
  "x_sensegnat_subject_id": "alice",
  "x_sensegnat_finding_count": 2,
  "x_sensegnat_severity": "medium",
  "x_sensegnat_score": 0.65,
  "x_sensegnat_finding_types": ["rare-destination"]
}
```

---

## Checking push results and handling errors

`push_findings` and `push_narratives` both return a `PushResult`:

```python
@dataclass
class PushResult:
    pushed: int           # number of objects sent in the bundle
    errors: list[str]     # empty on success
    ok: bool              # True when errors is empty (property)
```

Pattern for production use:

```python
import logging

logger = logging.getLogger(__name__)

result = connector.push_findings(findings)
if result.ok:
    logger.info("pushed %d finding(s) to GNAT", result.pushed)
else:
    for err in result.errors:
        logger.error("GNAT push error: %s", err)
    # decide whether to retry, queue, or alert
```

Error strings take one of these forms:

| Situation | Error string example |
|---|---|
| HTTP error response | `"HTTP 401: Unauthorized"` |
| Network failure | `"connection refused"` |
| DNS / timeout | `"[Errno -2] Name or service not known"` |

The connector does not retry automatically. Add retry logic at the call site if
your environment requires it.

Pushing an empty list always returns `PushResult(pushed=0)` without making a
network call — safe to call unconditionally.

---

## Record-only mode for local development

When `base_url` or `api_key` is empty, the connector skips all HTTP calls. Use
this mode during development and testing to inspect the STIX output without a
live GNAT instance:

```python
connector = GNATConnector()   # no base_url, no api_key

stix_dict = connector.to_record(finding)
print(stix_dict["name"])                  # "sensegnat:rare-destination:alice"
print(stix_dict["x_sensegnat_severity"])  # "medium"
print(stix_dict["x_sensegnat_evidence"])  # {"destination": ..., "port": ...}
```

`SenseGNATService` uses record-only mode by default (it constructs
`GNATConnector()` with no arguments). The list returned by `run_once()` is a
list of these STIX dicts — inspect them without any network dependency.

```python
service = SenseGNATService(adapter=adapter)
records = service.run_once()

indicators = [r for r in records if r["type"] == "indicator"]
notes = [r for r in records if r["type"] == "note"]

for ind in indicators:
    print(ind["x_sensegnat_severity"], ind["x_sensegnat_summary"])
```

---

## What GNAT sees

Once the bundle is accepted, GNAT stores each STIX object in the collection you
specified as `workspace`. GNAT queries this collection via TAXII and surfaces:

- **Indicators** with `x_gnat_sensor_type = "ids_alert"` appear in the threat
  intelligence feed filtered by sensor type.
- `x_gnat_signature` (`"rare-destination"`, `"peer-deviation"`, etc.) is
  exposed as the detection signature name.
- `x_gnat_tags` contains the subject ID, making findings filterable by entity.
- `x_gnat_tlp` controls sharing permissions within GNAT's TLP enforcement.

SenseGNAT-prefixed properties (`x_sensegnat_*`) are GNAT-visible as custom
object properties. Use GNAT's object detail view to inspect the full evidence
dict, severity, and score for each indicator.

---

## Authentication notes

The connector sends credentials as a Bearer token:

```
Authorization: Bearer <api_key>
Content-Type: application/stix+json;version=2.1
Accept: application/taxii+json;version=2.1
```

Do not hardcode the API key in source files. Load it from an environment
variable or secret store and pass it to `GNATConnector`:

```python
import os

connector = GNATConnector(
    base_url=os.environ["GNAT_BASE_URL"],
    api_key=os.environ["GNAT_API_KEY"],
)
```
