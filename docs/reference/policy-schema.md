# Policy Schema Reference

Policy rules are loaded from a YAML file by `PolicyEngine`. The path to the file is set via `policy_path` in `SenseGNATSettings`, or passed directly to `PolicyEngine.from_yaml(path)`.

**Module:** `sensegnat/policy/engine.py`

---

## Top-level structure

```yaml
groups:    # optional
  <group-name>:
    ...

subjects:  # optional
  <subject-id>:
    ...
```

Both `groups` and `subjects` are optional. An empty or absent policy file is valid; it results in no rules for any subject.

---

## `groups.<name>`

Defines rules that apply to all members of the named group.

```yaml
groups:
  <name>:
    members:               # list[str]  — subject IDs belonging to this group
    allowed_destinations:  # list[str]  — IP addresses treated as known-good
    allowed_ports:         # list[int]  — port numbers treated as known-good
    allowed_protocols:     # list[str]  — protocol names treated as known-good
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `members` | `list[str]` | No | Subject IDs in this group. Used by `PolicyEngine.peer_members()` to resolve peer profiles for `PeerDeviationDetector`. |
| `allowed_destinations` | `list[str]` | No | IP addresses that are known-good for all group members. |
| `allowed_ports` | `list[int]` | No | Port numbers that are known-good for all group members. |
| `allowed_protocols` | `list[str]` | No | Protocol names that are known-good for all group members. |

All fields are optional. Omitted list fields default to empty.

---

## `subjects.<id>`

Defines rules that apply to a single subject. The `<id>` must match the canonical `subject_id` (`source_user or source_host`) as used in the pipeline.

```yaml
subjects:
  <subject-id>:
    peer_group:            # str       — group to compare against for peer deviation
    allowed_destinations:  # list[str] — adds to (not replaces) group destinations
    allowed_ports:         # list[int] — adds to (not replaces) group ports
    allowed_protocols:     # list[str] — adds to (not replaces) group protocols
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `peer_group` | `str` | No | Name of the group this subject belongs to. Sets `BehaviorProfile.peer_group`. Used to look up peer profiles for `PeerDeviationDetector`. |
| `allowed_destinations` | `list[str]` | No | Subject-specific destinations added to the group's allow-list. |
| `allowed_ports` | `list[int]` | No | Subject-specific ports added to the group's allow-list. |
| `allowed_protocols` | `list[str]` | No | Subject-specific protocols added to the group's allow-list. |

---

## Resolution rules

When `PolicyEngine` resolves rules for a subject, it unions subject-level and group-level entries.

```
resolved_destinations(subject) =
    subjects.<subject>.allowed_destinations
    ∪ groups.<peer_group>.allowed_destinations
```

The same union applies to `allowed_ports` and `allowed_protocols`.

**A destination is "allowed" if it appears in either the group rules or the subject rules.**

Subject rules do **not** replace group rules. There is no override or exclusion mechanism; only addition.

### Resolution example

Given:
```yaml
groups:
  engineering:
    allowed_destinations: [10.0.0.1, 203.0.113.10]
    allowed_ports: [22, 443]

subjects:
  alice:
    peer_group: engineering
    allowed_destinations: [198.51.100.44]
    allowed_ports: [8443]
```

Resolved for `alice`:
- `allowed_destinations` = `{10.0.0.1, 203.0.113.10, 198.51.100.44}`
- `allowed_ports` = `{22, 443, 8443}`

### Missing policy

If a subject has no entry in `subjects`, `PolicyEngine.allowed_destinations(subject_id)` returns an empty `frozenset`. `PolicyViolationDetector` treats an empty frozenset as "no policy defined" and does not fire.

---

## PolicyEngine methods

| Method | Returns | Description |
|---|---|---|
| `peer_group(subject_id)` | `str \| None` | The `peer_group` value from the subject entry, or `None`. |
| `peer_members(group)` | `list[str]` | The `members` list for the named group. |
| `allowed_destinations(subject_id)` | `frozenset[str]` | Resolved union of subject + group destinations. |
| `allowed_ports(subject_id)` | `frozenset[int]` | Resolved union of subject + group ports. |
| `allowed_protocols(subject_id)` | `frozenset[str]` | Resolved union of subject + group protocols. |

---

## Profile seeding

Before telemetry events are processed, `ProfileBuilder` calls `PolicyEngine` to seed `BehaviorProfile` objects. The resolved `allowed_destinations`, `allowed_ports`, and `allowed_protocols` for each known subject are written directly into `common_destinations`, `common_ports`, and `common_protocols`. This means policy-allowed addresses do not trigger `RareDestinationDetector` on first contact.

---

## Complete annotated example

```yaml
# Policy file for SenseGNAT.
# Loaded by PolicyEngine.from_yaml(path) or via policy_path in settings.

groups:

  engineering:
    # All members share these rules.
    members: [alice, bob]
    allowed_destinations:
      - 203.0.113.10   # internal CI server
      - 10.0.0.1       # corporate gateway
    allowed_ports: [22, 80, 443, 8080]
    allowed_protocols: [tcp]

  finance:
    members: [carol]
    allowed_destinations:
      - 203.0.113.50   # finance SaaS endpoint
    allowed_ports: [443]
    allowed_protocols: [tcp]

subjects:

  alice:
    # alice is in the engineering group (inherits group rules)
    peer_group: engineering
    # alice has one additional approved destination not in the group list
    allowed_destinations:
      - 198.51.100.44  # alice's approved external vendor
    # alice is also allowed port 8443 (in addition to group ports)
    allowed_ports: [8443]
    # alice's resolved destinations: {203.0.113.10, 10.0.0.1, 198.51.100.44}
    # alice's resolved ports:        {22, 80, 443, 8080, 8443}
    # alice's resolved protocols:    {tcp}

  bob:
    # bob is in engineering; no subject-level additions
    peer_group: engineering
    # bob's resolved destinations: {203.0.113.10, 10.0.0.1}
    # bob's resolved ports:        {22, 80, 443, 8080}
    # bob's resolved protocols:    {tcp}

  carol:
    peer_group: finance
    # carol has no subject-level additions; inherits finance group rules only
    # carol's resolved destinations: {203.0.113.50}
    # carol's resolved ports:        {443}
    # carol's resolved protocols:    {tcp}
```

---

## Loader

```python
PolicyEngine.from_yaml(path: Path) -> PolicyEngine
```

Reads and `yaml.safe_load`s the file at `path`. Returns an empty `PolicyEngine` if the file is empty or contains only `null`. Does not validate field types; invalid entries (e.g., a string where a list is expected) will raise standard Python errors when the engine attempts to iterate them.
