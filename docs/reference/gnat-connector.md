# GNAT Connector Reference

`GNATConnector` publishes SenseGNAT findings and narratives into GNAT via TAXII 2.1. It converts `Finding` objects to STIX 2.1 Indicator dicts and `Narrative` objects to STIX 2.1 Note dicts, then POSTs them as a STIX bundle to the GNAT TAXII collection endpoint.

**Module:** `sensegnat/connectors/gnat_connector.py`

---

## GNATConnector

### Constructor

```python
GNATConnector(
    base_url:   str = "",
    api_key:    str = "",
    workspace:  str = "gnat",
    tlp:        str = "white",
    confidence: int = 75,
    timeout:    int = 30,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `base_url` | `str` | `""` | Root URL of the GNAT server, e.g. `"https://gnat.example.com"`. Trailing slash is stripped. |
| `api_key` | `str` | `""` | Bearer token for GNAT API authentication. |
| `workspace` | `str` | `"gnat"` | TAXII collection/workspace name used in the endpoint path. |
| `tlp` | `str` | `"white"` | TLP marking applied to all STIX objects. |
| `confidence` | `int` | `75` | STIX confidence score (0–100) on all Indicator objects. |
| `timeout` | `int` | `30` | HTTP request timeout in seconds. |

When `base_url` or `api_key` is empty, all push methods log a warning and return an empty `PushResult` without making network calls. `to_record()` and `narrative_to_record()` still function normally.

---

## Methods

### `finding_to_stix(finding: Finding) -> dict`

Converts a `Finding` to a STIX 2.1 Indicator dict. No network call.

See [STIX Indicator fields](#stix-indicator-fields-for-findings) below for the complete output schema.

---

### `narrative_to_stix(narrative: Narrative) -> dict`

Converts a `Narrative` to a STIX 2.1 Note dict. No network call.

See [STIX Note fields](#stix-note-fields-for-narratives) below for the complete output schema.

---

### `push_findings(findings: list[Finding]) -> PushResult`

Converts each `Finding` to a STIX Indicator via `finding_to_stix`, wraps all objects in a STIX bundle, and POSTs the bundle to the TAXII endpoint.

Returns an empty `PushResult` immediately if `findings` is empty.

---

### `push_narratives(narratives: list[Narrative]) -> PushResult`

Converts each `Narrative` to a STIX Note via `narrative_to_stix`, wraps all objects in a STIX bundle, and POSTs the bundle to the TAXII endpoint.

Returns an empty `PushResult` immediately if `narratives` is empty.

---

### `to_record(finding: Finding) -> dict`

Alias for `finding_to_stix`. Returns the STIX Indicator dict without making any network call. Provided for backwards compatibility.

---

### `narrative_to_record(narrative: Narrative) -> dict`

Alias for `narrative_to_stix`. Returns the STIX Note dict without making any network call. Provided for backwards compatibility.

---

## TAXII Transport

### Endpoint

```
POST {base_url}/taxii2/roots/gnat/collections/{workspace}/objects/
```

### Request headers

| Header | Value |
|---|---|
| `Authorization` | `Bearer {api_key}` |
| `Content-Type` | `application/stix+json;version=2.1` |
| `Accept` | `application/taxii+json;version=2.1` |

### Bundle envelope

All objects are wrapped in a STIX 2.1 bundle before posting:

```json
{
  "type": "bundle",
  "id": "bundle--{uuid4}",
  "spec_version": "2.1",
  "objects": [ ... ]
}
```

---

## PushResult

```python
@dataclass
class PushResult:
    pushed: int       = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors
```

| Attribute | Type | Description |
|---|---|---|
| `pushed` | `int` | Number of objects in a successful push. `0` on failure or when no objects were sent. |
| `errors` | `list[str]` | Error messages. Empty on success. |
| `ok` | `bool` (property) | `True` if `errors` is empty. |

### Error conditions

| Condition | `errors` content |
|---|---|
| HTTP error (4xx, 5xx) | `"HTTP {code}: {reason}"` |
| Network/OS error | `str(exc)` |
| No `base_url`/`api_key` configured | No error recorded; push is silently skipped. |

---

## STIX Indicator fields (for findings)

Produced by `finding_to_stix(finding)`.

### Standard STIX 2.1 fields

| Field | Type | Value |
|---|---|---|
| `type` | `str` | `"indicator"` |
| `spec_version` | `str` | `"2.1"` |
| `id` | `str` | `"indicator--{uuid4}"` (fresh UUID per call) |
| `created` | `str` | ISO 8601 UTC timestamp at time of serialization |
| `modified` | `str` | Same as `created` |
| `name` | `str` | `"sensegnat:{finding_type}:{subject_id}"` |
| `pattern` | `str` | See pattern rules below |
| `pattern_type` | `str` | `"stix"` |
| `valid_from` | `str` | `finding.seen_at.isoformat()` |
| `indicator_types` | `list[str]` | `["anomalous-activity"]` |
| `confidence` | `int` | Configured `confidence` value |

### GNAT custom fields

| Field | Type | Value |
|---|---|---|
| `x_gnat_sensor_type` | `str` | `"ids_alert"` |
| `x_gnat_sensor_id` | `str` | `"sensegnat"` |
| `x_gnat_signature` | `str` | `finding.finding_type` |
| `x_gnat_tags` | `list[str]` | `[finding.subject_id]` |
| `x_gnat_tlp` | `str` | Configured `tlp` value |

### SenseGNAT custom fields

| Field | Type | Value |
|---|---|---|
| `x_sensegnat_finding_id` | `str` | `finding.finding_id` |
| `x_sensegnat_score` | `float` | `finding.score` |
| `x_sensegnat_severity` | `str` | `finding.severity` |
| `x_sensegnat_summary` | `str` | `finding.summary` |
| `x_sensegnat_evidence` | `dict[str, str]` | `finding.evidence` |
| `x_sensegnat_subject_id` | `str` | `finding.subject_id` |

### Pattern rules

```python
if "destination" in finding.evidence:
    pattern = f"[ipv4-addr:value = '{finding.evidence['destination']}']"
else:
    pattern = f"[x-sensegnat-subject:id = '{finding.subject_id}']"
```

Detectors that populate `evidence["destination"]` (all except `TimeWindowDriftDetector`) produce an IPv4 pattern. `TimeWindowDriftDetector` produces a subject-keyed pattern.

---

## STIX Note fields (for narratives)

Produced by `narrative_to_stix(narrative)`.

### Standard STIX 2.1 fields

| Field | Type | Value |
|---|---|---|
| `type` | `str` | `"note"` |
| `spec_version` | `str` | `"2.1"` |
| `id` | `str` | `"note--{uuid4}"` (fresh UUID per call) |
| `created` | `str` | ISO 8601 UTC timestamp at time of serialization |
| `modified` | `str` | Same as `created` |
| `content` | `str` | `narrative.summary` |
| `object_refs` | `list` | `[]` (empty — no specific STIX objects referenced) |

### GNAT / SenseGNAT custom fields

| Field | Type | Value |
|---|---|---|
| `x_gnat_sensor_id` | `str` | `"sensegnat"` |
| `x_gnat_tlp` | `str` | Configured `tlp` value |
| `x_sensegnat_subject_id` | `str` | `narrative.subject_id` |
| `x_sensegnat_finding_count` | `int` | `narrative.finding_count` |
| `x_sensegnat_severity` | `str` | `narrative.severity` |
| `x_sensegnat_score` | `float` | `narrative.score` |
| `x_sensegnat_finding_types` | `list[str]` | `list(narrative.finding_types)` |

---

## Example STIX Indicator

```json
{
  "type": "indicator",
  "spec_version": "2.1",
  "id": "indicator--a3b4c5d6-e7f8-9012-abcd-ef1234567890",
  "created": "2024-01-15T12:05:00.123456+00:00",
  "modified": "2024-01-15T12:05:00.123456+00:00",
  "name": "sensegnat:rare-destination:alice",
  "pattern": "[ipv4-addr:value = '198.51.100.99']",
  "pattern_type": "stix",
  "valid_from": "2024-01-15T12:05:00.123456+00:00",
  "indicator_types": ["anomalous-activity"],
  "confidence": 75,
  "x_gnat_sensor_type": "ids_alert",
  "x_gnat_sensor_id": "sensegnat",
  "x_gnat_signature": "rare-destination",
  "x_gnat_tags": ["alice"],
  "x_gnat_tlp": "white",
  "x_sensegnat_finding_id": "f1234567-89ab-cdef-0123-456789abcdef",
  "x_sensegnat_score": 0.65,
  "x_sensegnat_severity": "medium",
  "x_sensegnat_summary": "alice contacted a rare destination 198.51.100.99",
  "x_sensegnat_evidence": {
    "destination": "198.51.100.99",
    "port": "8080",
    "protocol": "tcp"
  },
  "x_sensegnat_subject_id": "alice"
}
```

---

## Example STIX Note

```json
{
  "type": "note",
  "spec_version": "2.1",
  "id": "note--b4c5d6e7-f8a9-0123-bcde-f12345678901",
  "created": "2024-01-15T12:05:01.000000+00:00",
  "modified": "2024-01-15T12:05:01.000000+00:00",
  "content": "alice: 4 finding(s) — rare-destination ×3, peer-deviation. Severity: medium, peak score: 0.70.",
  "object_refs": [],
  "x_gnat_sensor_id": "sensegnat",
  "x_gnat_tlp": "white",
  "x_sensegnat_subject_id": "alice",
  "x_sensegnat_finding_count": 4,
  "x_sensegnat_severity": "medium",
  "x_sensegnat_score": 0.70,
  "x_sensegnat_finding_types": ["rare-destination", "peer-deviation"]
}
```
