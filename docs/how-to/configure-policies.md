# How to configure policies

This guide shows you how to write a YAML policy file, load it into
`PolicyEngine`, and verify it is seeding behavioral baselines correctly.

---

## What policies do

Policies seed `BehaviorProfile` objects with known-good traffic before any
telemetry is observed. A destination, port, or protocol listed as allowed in
policy is treated as part of the baseline from the first event. This means
traffic to your internal DNS server or corporate proxy will never fire a
`rare-destination` finding, even on the very first run.

Policies do not suppress findings on their own. The `PolicyViolationDetector`
actually fires the other way: it flags traffic that is *outside* an explicit
allow-list. The two behaviours are complementary.

---

## Policy file structure

```yaml
groups:
  <group_name>:
    members: [<subject_id>, ...]
    allowed_destinations: [<ip_or_host>, ...]
    allowed_ports: [<int>, ...]
    allowed_protocols: [<proto>, ...]

subjects:
  <subject_id>:
    peer_group: <group_name>
    allowed_destinations: [...]
    allowed_ports: [...]
    allowed_protocols: [...]
```

All keys under both `groups` and `subjects` are optional. Omit
`allowed_destinations` if you do not want to constrain destinations for that
group or subject; the `PolicyViolationDetector` only fires when the allow-list
is non-empty.

---

## Minimal policy file

```yaml
groups:
  engineering:
    members: [alice, bob]
    allowed_ports: [22, 80, 443]
    allowed_protocols: [tcp]

subjects:
  alice:
    peer_group: engineering
  bob:
    peer_group: engineering
```

This is enough to:
- assign alice and bob to the `engineering` peer group (required for
  `PeerDeviationDetector` to compare them)
- seed their profiles with ports 22, 80, 443 and protocol `tcp` before any
  events arrive

---

## Full annotated example

This is an expanded version of `examples/sensegnat.example.policies.yaml`.

```yaml
# Group rules apply to every member of the group.
# Subject rules ADD to group rules — they do not replace them.

groups:
  engineering:
    members: [alice, bob]
    allowed_destinations:
      - 203.0.113.10    # internal build server
      - 10.0.0.1        # corporate proxy
    allowed_ports: [22, 80, 443, 8080]
    allowed_protocols: [tcp]

  finance:
    members: [carol]
    allowed_destinations:
      - 203.0.113.50    # finance SaaS endpoint
    allowed_ports: [443]
    allowed_protocols: [tcp]

subjects:
  alice:
    peer_group: engineering
    # alice's additional exceptions on top of engineering group rules
    allowed_destinations:
      - 198.51.100.44   # approved external vendor
    allowed_ports: [8443]

  bob:
    peer_group: engineering
    # no subject-level exceptions — inherits engineering rules only

  carol:
    peer_group: finance
    # no subject-level exceptions — inherits finance rules only
```

---

## How group inheritance works

Subject rules are **additive**. When you call `policy_engine.allowed_destinations("alice")`,
the engine unions alice's subject-level destinations with the destinations from
her group:

```
alice's effective destinations
  = subjects.alice.allowed_destinations
  + groups.engineering.allowed_destinations
  = {198.51.100.44} ∪ {203.0.113.10, 10.0.0.1}
  = {198.51.100.44, 203.0.113.10, 10.0.0.1}
```

The same union logic applies to ports and protocols.

| Subject | Source | Effective destinations |
|---|---|---|
| `alice` | group + subject | `{203.0.113.10, 10.0.0.1, 198.51.100.44}` |
| `bob` | group only | `{203.0.113.10, 10.0.0.1}` |
| `carol` | group only | `{203.0.113.50}` |

A subject with `peer_group` set but no group-level or subject-level
`allowed_destinations` gets an empty frozenset for destinations —
`PolicyViolationDetector` will not fire for that subject on destination checks.

---

## Loading the policy in code

```python
from pathlib import Path
from sensegnat.policy.engine import PolicyEngine

engine = PolicyEngine.from_yaml(Path("policies.yaml"))
```

Verify the engine loaded correctly with quick assertions:

```python
assert engine.peer_group("alice") == "engineering"
assert "203.0.113.10" in engine.allowed_destinations("alice")
assert "198.51.100.44" in engine.allowed_destinations("alice")
assert "198.51.100.44" not in engine.allowed_destinations("bob")
assert 443 in engine.allowed_ports("alice")
assert "tcp" in engine.allowed_protocols("carol")
```

For a subject that does not appear in the policy file at all:

```python
assert engine.peer_group("ghost") is None
assert engine.allowed_destinations("ghost") == frozenset()
```

---

## Wiring the engine into the service

**Option 1 — via settings YAML (recommended for production)**

Add `policy_path` to your `sensegnat.yaml`:

```yaml
policy_path: ./policies.yaml
```

Then load it normally:

```python
from pathlib import Path
from sensegnat.api.service import SenseGNATService
from sensegnat.config.settings import load_settings
from sensegnat.ingestion.csv_adapter import CsvEventAdapter

settings = load_settings(Path("sensegnat.yaml"))
service = SenseGNATService(adapter=CsvEventAdapter(Path("events.csv")), settings=settings)
service.run_once()
```

`SenseGNATService.__init__` reads `settings.policy_path` and calls
`PolicyEngine.from_yaml` automatically.

**Option 2 — directly on the service instance**

```python
from sensegnat.policy.engine import PolicyEngine

service = SenseGNATService(adapter=adapter)
service.policy_engine = PolicyEngine.from_yaml(Path("policies.yaml"))
```

This is useful in tests or one-off scripts where you want to avoid the settings
layer.

---

## Common patterns

### Allow-listing shared cloud infrastructure

Put widely used cloud endpoints in a group that all affected subjects belong to,
rather than duplicating them in every subject block:

```yaml
groups:
  all_staff:
    members: [alice, bob, carol, dave]
    allowed_destinations:
      - 8.8.8.8           # Google DNS
      - 1.1.1.1           # Cloudflare DNS
      - 169.254.169.254   # AWS metadata service
    allowed_ports: [53, 443, 80]
    allowed_protocols: [tcp, udp]
```

### Segmenting by department

Give each department its own group with tightly scoped destinations. Subjects
that belong to multiple logical groups cannot be in two `peer_group` values
simultaneously; put shared rules in a parent group and document the exception:

```yaml
groups:
  developers:
    members: [alice, bob]
    allowed_ports: [22, 80, 443, 8080, 8443, 5432]

  analysts:
    members: [carol, dave]
    allowed_ports: [443, 3306, 5432]
```

### Handling one-off exceptions

Put per-subject exceptions directly in the `subjects` block rather than
modifying group rules. This keeps the group definition clean and the exception
auditable:

```yaml
subjects:
  alice:
    peer_group: developers
    allowed_destinations:
      - 198.51.100.44   # temporary vendor access, expires 2026-06-01
    allowed_ports: [8443]
```

### Subjects without a peer group

You can define `allowed_destinations` for a subject without assigning them a
`peer_group`. `PeerDeviationDetector` will not fire for that subject (no peers
to compare against), but `PolicyViolationDetector` will still enforce the
allow-list:

```yaml
subjects:
  service_account_x:
    allowed_destinations:
      - 10.10.0.5
    allowed_ports: [443]
    allowed_protocols: [tcp]
```

---

## Verifying policy seeding suppresses rarity findings

The easiest way to confirm that policy seeding is working is to run two
consecutive `run_once()` calls on the same service instance. On the first run,
a policy-seeded destination is included in the built profile. On the second run,
the same destination appears in the existing profile and the rarity detector
stays silent:

```python
from datetime import datetime, timezone
from sensegnat.api.service import SenseGNATService
from sensegnat.ingestion.sample_adapter import SampleEventAdapter
from sensegnat.policy.engine import PolicyEngine
from pathlib import Path

service = SenseGNATService(adapter=SampleEventAdapter())
service.policy_engine = PolicyEngine.from_yaml(Path("policies.yaml"))

service.run_once()   # builds profiles seeded with policy destinations

# Replace the adapter with events pointing at policy-allowed destinations
# and confirm no rare-destination findings are emitted.
```

If you see `rare-destination` findings for policy-listed destinations on the
second run, the most likely cause is that the subject identifier in the event
(`source_user or source_host`) does not match the subject key in the policy
file. Print `engine.peer_group(subject_id)` to check.
