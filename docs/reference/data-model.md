# Data Model Reference

All core data objects are **frozen dataclasses** (`@dataclass(frozen=True)`). They are immutable after construction. Do not use Pydantic for data-plane objects; Pydantic is reserved for configuration models.

Sources: `sensegnat/models/`

---

## Subject Identity

Throughout the system the canonical `subject_id` is derived from a `NormalizedNetworkEvent` as:

```python
subject_id = event.source_user or event.source_host
```

`source_user` takes precedence when present. All profiles, findings, and narratives are keyed to this value. Detectors, the `ProfileBuilder`, and `NarrativeBuilder` all apply the same rule.

---

## NormalizedNetworkEvent

**Module:** `sensegnat/models/events.py`

The unit of telemetry passed through the pipeline. Every adapter produces instances of this class.

```python
@dataclass(frozen=True)
class NormalizedNetworkEvent:
    event_id:         str
    seen_at:          datetime
    source_host:      str
    source_user:      str | None
    destination:      str
    destination_port: int
    protocol:         str
    bytes_out:        int = 0
    bytes_in:         int = 0
```

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `event_id` | `str` | — | Unique identifier for the event. Adapters use the source-native ID (e.g., Zeek `uid`, Suricata `flow_id`) or generate a UUID. |
| `seen_at` | `datetime` | — | Observation timestamp. Always timezone-aware (UTC). |
| `source_host` | `str` | — | Originating host; IPv4, hostname, or FQDN as provided by the source. |
| `source_user` | `str \| None` | — | Authenticated user identity if available. `None` when the source carries no user context (e.g., Zeek conn.log, Suricata EVE). |
| `destination` | `str` | — | Destination IPv4 address. |
| `destination_port` | `int` | — | Destination TCP/UDP port. |
| `protocol` | `str` | — | Transport protocol, lowercased: `"tcp"`, `"udp"`, `"icmp"`, etc. |
| `bytes_out` | `int` | `0` | Bytes sent from source to destination. `0` when not available. |
| `bytes_in` | `int` | `0` | Bytes received from destination by source. `0` when not available. |

### Notes

- `seen_at` must be timezone-aware. Adapters that parse naive timestamps attach `timezone.utc` before constructing the event.
- `protocol` is always lowercased at parse time by all built-in adapters.
- `bytes_out` and `bytes_in` are informational; no detector currently fires on byte counts alone.

---

## BehaviorProfile

**Module:** `sensegnat/models/entities.py`

A per-subject behavioral baseline accumulating the set of destinations, ports, and protocols observed over the profiling window.

```python
@dataclass(frozen=True)
class BehaviorProfile:
    profile_id:           str
    subject_id:           str
    peer_group:           str | None        = None
    common_destinations:  FrozenSet[str]    = frozenset()
    common_ports:         FrozenSet[int]    = frozenset()
    common_protocols:     FrozenSet[str]    = frozenset()
```

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `profile_id` | `str` | — | Unique identifier for this profile record. Typically `"profile-{subject_id}"`. |
| `subject_id` | `str` | — | The canonical subject this profile describes (`source_user or source_host`). |
| `peer_group` | `str \| None` | `None` | Name of the peer group this subject belongs to. `None` if the subject is not in any group. Empty string is also accepted but `None` is canonical for "no group". |
| `common_destinations` | `FrozenSet[str]` | `frozenset()` | Set of destination IP addresses seen for this subject. |
| `common_ports` | `FrozenSet[int]` | `frozenset()` | Set of destination ports seen for this subject. |
| `common_protocols` | `FrozenSet[str]` | `frozenset()` | Set of transport protocols seen for this subject. |

### Methods

#### `merge(incoming: BehaviorProfile) -> BehaviorProfile`

Returns a **new** `BehaviorProfile` whose observation sets are the union of `self` and `incoming`. The `profile_id` and `subject_id` from `self` are preserved. The `peer_group` from `incoming` is used, allowing policy updates to propagate on re-seed.

```python
merged = existing.merge(incoming)
# merged.profile_id == existing.profile_id
# merged.subject_id == existing.subject_id
# merged.peer_group == incoming.peer_group
# merged.common_destinations == existing.common_destinations | incoming.common_destinations
```

`merge` is called by the JSON-backed store's `put_many` to accumulate profiles across runs without discarding historical observations.

### Notes

- The `FrozenSet` fields are immutable. Profiling produces new instances rather than mutating existing ones.
- Policy seeding populates these sets from YAML rules before any telemetry is processed, so detectors do not fire on first contact with known-good addresses.

---

## Finding

**Module:** `sensegnat/models/findings.py`

The output of a single detector invocation. Represents one discrete anomaly observation.

```python
@dataclass(frozen=True)
class Finding:
    finding_id:   str
    finding_type: str
    seen_at:      datetime
    subject_id:   str
    severity:     str
    score:        float
    summary:      str
    evidence:     dict[str, str]
```

### Fields

| Field | Type | Description |
|---|---|---|
| `finding_id` | `str` | UUID string (`str(uuid4())`). Unique per finding instance. |
| `finding_type` | `str` | Machine-readable detector identifier. See values below. |
| `seen_at` | `datetime` | When the finding was produced. Always UTC, set by `utcnow()`. |
| `subject_id` | `str` | Canonical subject this finding is about. |
| `severity` | `str` | One of: `"low"`, `"medium"`, `"high"`, `"critical"`. |
| `score` | `float` | Confidence/risk score in the range `0.0`–`1.0`. |
| `summary` | `str` | Human-readable one-line description of the finding. |
| `evidence` | `dict[str, str]` | Key-value pairs that support the finding. All values are strings. |

### `finding_type` values

| Value | Produced by |
|---|---|
| `"rare-destination"` | `RareDestinationDetector` |
| `"peer-deviation"` | `PeerDeviationDetector` |
| `"policy-violation"` | `PolicyViolationDetector` |
| `"time-window-drift"` | `TimeWindowDriftDetector` |

### Severity ordering

Used by `NarrativeBuilder` to roll up the highest severity across findings:

```
low(0) < medium(1) < high(2) < critical(3)
```

### Notes

- `evidence` values are always `str`. Numeric values (port numbers, scores) are converted by detectors before storage.
- All detectors set `seen_at` to `utcnow()` at detection time, not the `seen_at` of the triggering event.

---

## Narrative

**Module:** `sensegnat/models/narratives.py`

A per-subject summary rolled up across all findings for that subject in a single pipeline run. Produced by `NarrativeBuilder`.

```python
@dataclass(frozen=True)
class Narrative:
    subject_id:    str
    finding_count: int
    finding_types: tuple[str, ...]
    severity:      str
    score:         float
    summary:       str
```

### Fields

| Field | Type | Description |
|---|---|---|
| `subject_id` | `str` | The subject this narrative covers. |
| `finding_count` | `int` | Total number of findings rolled into this narrative. |
| `finding_types` | `tuple[str, ...]` | Distinct finding types ordered by frequency, most common first. |
| `severity` | `str` | Highest severity value across all findings (`"low"`, `"medium"`, `"high"`, `"critical"`). |
| `score` | `float` | Peak score across all findings (`0.0`–`1.0`). |
| `summary` | `str` | Human-readable summary. Format: `"{subject}: {N} finding(s) — {type_freq}. Severity: {sev}, peak score: {score:.2f}."` where `type_freq` lists types with counts, e.g. `"rare-destination ×3, peer-deviation ×1"`. |

### Example `summary`

```
alice: 4 finding(s) — rare-destination ×3, peer-deviation. Severity: medium, peak score: 0.70.
```

### Notes

- `NarrativeBuilder.build()` returns `None` if `findings` is empty.
- `finding_types` uses `Counter.most_common()` ordering; ties are broken by insertion order (CPython dict stability).
- The `summary` omits the `×N` suffix when a type appears exactly once.

---

## NetworkEntity

**Module:** `sensegnat/models/entities.py`

An auxiliary model for representing network entities. Not used in the core detection pipeline.

```python
@dataclass(frozen=True)
class NetworkEntity:
    entity_id:    str
    entity_type:  str
    display_name: str
    attributes:   dict[str, str] = field(default_factory=dict)
```

| Field | Type | Default | Description |
|---|---|---|---|
| `entity_id` | `str` | — | Unique identifier for the entity. |
| `entity_type` | `str` | — | Entity classification (e.g., `"host"`, `"user"`). |
| `display_name` | `str` | — | Human-readable label. |
| `attributes` | `dict[str, str]` | `{}` | Arbitrary key-value metadata. |
