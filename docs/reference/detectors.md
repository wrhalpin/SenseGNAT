# Detectors Reference

All detectors live in `sensegnat/detection/`. Each detector is a stateless class with a `detect(...)` method that returns a `Finding` or `None`. Detectors do not share state with each other or across calls.

All detectors satisfy the explainability requirement (ADR-003): every `Finding` produced has a non-empty human-readable `summary` and a populated `evidence` dict.

---

## Comparison Table

| Detector | Compares | Severity | Score | Requires profile? | Requires policy? |
|---|---|---|---|---|---|
| `RareDestinationDetector` | Event destination vs. subject's known destinations | `medium` | `0.65` | Yes | No |
| `PeerDeviationDetector` | Event destination/port vs. peer group's known destinations/ports | `medium` | `0.70` | Yes (subject + peers) | No |
| `PolicyViolationDetector` | Event destination/port vs. per-subject allow-list | `high` | `0.90` | No | Yes |
| `TimeWindowDriftDetector` | Batch novel destinations vs. established profile size | `medium` | variable (≤ 1.0) | Yes | No |

---

## RareDestinationDetector

**Module:** `sensegnat/detection/rarity.py`

Flags contacts with destinations not previously present in the subject's behavioral profile.

### Signature

```python
def detect(
    self,
    event: NormalizedNetworkEvent,
    profile: BehaviorProfile | None,
) -> Finding | None
```

### Logic

1. If `profile is None` → return `None` (no baseline to compare against).
2. If `event.destination in profile.common_destinations` → return `None` (known destination).
3. Otherwise → return a `Finding`.

### Finding properties

| Property | Value |
|---|---|
| `finding_type` | `"rare-destination"` |
| `severity` | `"medium"` |
| `score` | `0.65` |
| `summary` | `"{subject_id} contacted a rare destination {destination}"` |

### Evidence keys

| Key | Value |
|---|---|
| `destination` | The destination IP address |
| `port` | Destination port (as string) |
| `protocol` | Transport protocol |

### Notes

- Does not fire for new subjects with no profile yet. The caller must build a profile (even an empty one seeded by policy) before this detector is meaningful.
- `subject_id` is resolved as `event.source_user or event.source_host` inside the detector.

---

## PeerDeviationDetector

**Module:** `sensegnat/detection/peer_deviation.py`

Flags behavior that diverges from what peers in the same group have been observed doing. Checks both destination and port against the union of all peer profiles.

### Signature

```python
def detect(
    self,
    event: NormalizedNetworkEvent,
    profile: BehaviorProfile | None,
    peer_profiles: list[BehaviorProfile] | None = None,
) -> Finding | None
```

### Logic

1. If `profile is None` or `peer_profiles` is empty/None → return `None`.
2. Compute `peer_destinations`: union of `common_destinations` across all `peer_profiles`.
3. Compute `peer_ports`: union of `common_ports` across all `peer_profiles`.
4. If `event.destination` is in `peer_destinations` **and** `event.destination_port` is in `peer_ports` → return `None`.
5. Otherwise → return a `Finding` describing which dimensions deviated.

### Finding properties

| Property | Value |
|---|---|
| `finding_type` | `"peer-deviation"` |
| `severity` | `"medium"` |
| `score` | `0.70` |
| `summary` | `"{subject_id} deviated from peer group: {deviation_list}"` |

### Evidence keys

Evidence keys are conditionally populated based on what deviated:

| Key | Present when | Value |
|---|---|---|
| `peer_group` | Always | `profile.peer_group` or `"unknown"` |
| `peer_count` | Always | Number of peer profiles examined (as string) |
| `destination` | Destination deviated | The destination IP address |
| `port` | Port deviated | Destination port (as string) |

### Notes

- A finding fires if **either** the destination or the port deviates from peers — both do not need to deviate simultaneously.
- The detector does not check the subject's own profile, only the peer union. A subject can contact a destination it has seen before but still trigger peer deviation if peers have never seen it.
- Peer profiles are provided by the caller (`SenseGNATService`), which queries the profile store for all members of the subject's peer group.

---

## PolicyViolationDetector

**Module:** `sensegnat/detection/policy_violation.py`

Flags events that contact destinations or ports outside the subject's policy allow-list. Only fires when a non-empty allow-list exists for the subject — an absent or empty policy is never treated as a violation.

### Signature

```python
def detect(
    self,
    event: NormalizedNetworkEvent,
    policy_engine: PolicyEngine | None,
) -> Finding | None
```

### Logic

1. If `policy_engine is None` → return `None`.
2. Resolve `allowed_destinations` and `allowed_ports` for the subject (via `PolicyEngine`).
3. Destination violation: `bool(allowed_destinations) and event.destination not in allowed_destinations`.
4. Port violation: `bool(allowed_ports) and event.destination_port not in allowed_ports`.
5. If neither check fires → return `None`.
6. Otherwise → return a `Finding`.

### Finding properties

| Property | Value |
|---|---|
| `finding_type` | `"policy-violation"` |
| `severity` | `"high"` |
| `score` | `0.90` |
| `summary` | `"{subject_id} policy violation: {violation_list}"` |

### Evidence keys

Evidence keys are conditionally populated based on what was violated:

| Key | Present when | Value |
|---|---|---|
| `destination` | Destination violated | The destination IP address |
| `port` | Port violated | Destination port (as string) |

### Notes

- `allowed_protocols` is resolved by `PolicyEngine` but is **not currently checked** by this detector. Protocol violations do not produce findings.
- The "non-empty allow-list" guard prevents spurious findings for subjects with no policy entry. If `PolicyEngine.allowed_destinations(subject_id)` returns an empty frozenset, destination checks are skipped entirely.
- Subject-level and group-level rules are resolved and unioned by `PolicyEngine` before the detector receives them. The detector only sees the final resolved set.

---

## TimeWindowDriftDetector

**Module:** `sensegnat/detection/time_window_drift.py`

Flags subjects whose destination set expands unusually fast within a single processing window. Compares the count of novel destinations in the current batch to the size of the established profile.

### Constructor

```python
def __init__(
    self,
    expansion_threshold: float = 0.5,
    min_profile_size: int = 3,
) -> None
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `expansion_threshold` | `float` | `0.5` | Fraction of new destinations relative to established profile size that triggers a finding. `0.5` means "50% expansion". |
| `min_profile_size` | `int` | `3` | Minimum number of established destinations required before the detector will fire. Prevents false positives on thin profiles. |

### Signature

```python
def detect(
    self,
    subject_id: str,
    events: list[NormalizedNetworkEvent],
    profile: BehaviorProfile | None,
) -> Finding | None
```

Note: this detector takes `subject_id` and a list of events rather than a single event — it operates on a batch.

### Logic

1. If `profile is None` or `events` is empty → return `None`.
2. If `len(profile.common_destinations) < min_profile_size` → return `None`.
3. Compute `batch_destinations`: set of all destinations in `events`.
4. Compute `novel`: `batch_destinations - profile.common_destinations`.
5. If `novel` is empty → return `None`.
6. Compute `expansion_ratio = len(novel) / len(profile.common_destinations)`.
7. If `expansion_ratio < expansion_threshold` → return `None`.
8. Compute `score = min(round(expansion_ratio, 2), 1.0)`.
9. Return a `Finding`.

### Finding properties

| Property | Value |
|---|---|
| `finding_type` | `"time-window-drift"` |
| `severity` | `"medium"` |
| `score` | `min(expansion_ratio, 1.0)` — variable, capped at `1.0` |
| `summary` | `"{subject_id} contacted {N} novel destination(s) this window ({ratio}% expansion over {M}-destination profile)"` |

### Evidence keys

| Key | Value |
|---|---|
| `novel_destination_count` | Count of destinations in batch not in profile (as string) |
| `established_destination_count` | Count of destinations in established profile (as string) |
| `expansion_ratio` | `expansion_ratio` formatted to 2 decimal places |
| `expansion_threshold` | Configured threshold formatted to 2 decimal places |

### Example

With `expansion_threshold=0.5, min_profile_size=3`:

- Profile has 4 known destinations.
- Batch contains 3 novel destinations → `expansion_ratio = 3/4 = 0.75`.
- `0.75 >= 0.5` → finding fires with `score=0.75`.

With 6 novel destinations → `expansion_ratio = 1.5` → `score = min(1.5, 1.0) = 1.0`.

### Notes

- Score is computed per-batch from the ratio; it is not a fixed constant like other detectors.
- The detector does not require the events to belong to a single subject — the caller is responsible for filtering events by `subject_id` before passing them in.
- `SenseGNATService` calls this detector once per subject, passing all events for that subject in the current run.
