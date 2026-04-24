# Investigation Context Reference

SenseGNAT implements the shared investigation-context contract defined in the GNAT repo at `docs/reference/investigation-context-schema.md`. This page documents the SenseGNAT side of that contract.

---

## STIX custom properties

Three custom properties are stamped on every `indicator` and `note` that has investigation context. They are never present on findings that have no context (Path C).

| Property | Type | Value |
|---|---|---|
| `x_gnat_investigation_id` | string | GNAT investigation ID, e.g. `"IC-2026-0042"` |
| `x_gnat_investigation_origin` | string | Always `"sensegnat"` |
| `x_gnat_investigation_link_type` | string | `"confirmed"`, `"inferred"`, or `"suggested"` |

### Link type semantics

| Value | Meaning |
|---|---|
| `"confirmed"` | The policy rule was authored as part of this investigation. The analyst explicitly declared the association. |
| `"inferred"` | SenseGNAT associated the finding with the investigation based on subject matching (API lookup or Kafka hint). |
| `"suggested"` | Multi-match case: this investigation is a candidate but not the primary match. Listed in a companion `note`. |

---

## Data model

### `Finding`

`sensegnat/models/findings.py`

```python
@dataclass(frozen=True)
class Finding:
    finding_id: str
    finding_type: str
    seen_at: datetime
    subject_id: str
    severity: str
    score: float
    summary: str
    evidence: dict[str, str]
    investigation_id: str | None = None
    investigation_link_type: str | None = None
```

### `Narrative`

`sensegnat/models/narratives.py`

```python
@dataclass(frozen=True)
class Narrative:
    subject_id: str
    finding_count: int
    finding_types: tuple[str, ...]
    severity: str
    score: float
    summary: str
    investigation_id: str | None = None
    investigation_link_type: str | None = None
```

`NarrativeBuilder` propagates investigation context from the subject's findings. When multiple findings have different investigation IDs, the one with the highest-priority link type wins (`"confirmed"` > `"inferred"` > `"suggested"`).

### `NormalizedNetworkEvent`

`sensegnat/models/events.py`

```python
investigation_hint: str | None = None
```

Set by `GNATTelemetryAdapter` when the Kafka record carries `_gnat_investigation_hint`. Used by the enrichment pass in `SenseGNATService` as a fast-path for Path B that bypasses the GNAT API call.

---

## Configuration

`sensegnat/config/settings.py` — `InvestigationSettings`

```yaml
investigation:
  lookup_enabled: false          # master switch for Path B API lookup
  lookup_timeout_s: 2.0          # per-call timeout in seconds
  lookup_cache_ttl_s: 60         # subject → IDs cache window in seconds
  lookup_max_matches: 3          # cap on "suggested" candidates
```

All fields are optional. Defaults shown above.

---

## Policy rule fields

`investigation_id` and `investigation_link_type` are optional per-subject fields in the policy YAML. See the [Policy how-to](../how-to/attach-findings-to-investigations.md#path-a--declare-the-investigation-in-a-policy-rule-recommended) for the full YAML format.

---

## GNATConnector API

`sensegnat/connectors/gnat_connector.py`

### `finding_to_stix(finding) → dict`

Stamps `x_gnat_investigation_id`, `x_gnat_investigation_origin`, `x_gnat_investigation_link_type` when `finding.investigation_id` is set.

### `narrative_to_stix(narrative) → dict`

Same stamping as `finding_to_stix`. Indicator and its companion note always share the same investigation context.

### `make_grouping(investigation_id, object_refs, run_id) → dict`

Builds a STIX `grouping` object wrapping all tagged indicators and notes for one investigation in a single `run_once()` call.

### `find_investigations_for_subject(subject_ref, timeout_seconds=None) → list[str]`

Calls `GET /api/investigations?subject=<subject_ref>` on the GNAT server. Returns a list of investigation IDs. Returns `[]` on any error (timeout, network, missing credentials). Results are cached by subject for `lookup_cache_ttl_s` seconds.

---

## Attachment paths

| Path | Source | Link type | Requires |
|---|---|---|---|
| A | Policy rule `investigation_id` field | `"confirmed"` | Nothing — always active |
| B (hint) | `_gnat_investigation_hint` Kafka field | `"inferred"` | `GNATTelemetryAdapter` + GNAT enrichment |
| B (API) | `GET /api/investigations?subject=...` | `"inferred"` | `lookup_enabled: true` + GNAT endpoint |
| C | No context | (none) | Default |

Full how-to: [attach-findings-to-investigations](../how-to/attach-findings-to-investigations.md).
