# How to use persistent storage

This guide shows you how to switch from the default in-memory stores to
JSON-backed stores so that behavioral profiles and findings survive process
restarts.

---

## The two store pairs

SenseGNAT ships with two store implementations for both profiles and findings:

| Store class | Module | Persistence |
|---|---|---|
| `InMemoryProfileStore` | `sensegnat.storage.memory` | Process lifetime only |
| `InMemoryFindingStore` | `sensegnat.storage.memory` | Process lifetime only |
| `JsonProfileStore` | `sensegnat.storage.json_store` | JSON file on disk |
| `JsonFindingStore` | `sensegnat.storage.json_store` | JSON file on disk |

Both pairs implement the same interface, so they are drop-in replacements:

```python
# InMemoryProfileStore
store.get(subject_id) -> BehaviorProfile | None
store.put_many(profiles: dict[str, BehaviorProfile]) -> None
store.list_all() -> list[BehaviorProfile]   # InMemoryFindingStore equivalent: list_all()

# JsonProfileStore — identical interface
store.get(subject_id) -> BehaviorProfile | None
store.put_many(profiles: dict[str, BehaviorProfile]) -> None
```

---

## Switching to JSON-backed stores

### Option 1 — pass stores to `SenseGNATService` directly

```python
from pathlib import Path
from sensegnat.api.service import SenseGNATService
from sensegnat.ingestion.csv_adapter import CsvEventAdapter
from sensegnat.storage.json_store import JsonFindingStore, JsonProfileStore

profile_path = Path("./var/profiles.json")
finding_path = Path("./var/findings.json")

service = SenseGNATService(adapter=CsvEventAdapter(Path("events.csv")))
service.profile_store = JsonProfileStore(profile_path)
service.finding_store = JsonFindingStore(finding_path)

service.run_once()
```

The stores create their parent directories automatically when you call
`put_many` or `add` for the first time. You do not need to `mkdir` beforehand.

### Option 2 — configure via settings YAML (recommended)

When you pass a `SenseGNATSettings` object to `SenseGNATService`, the service
instantiates `JsonProfileStore` and `JsonFindingStore` automatically using the
paths from `settings.storage`:

```yaml
# sensegnat.yaml
storage:
  profile_store_path: ./var/profiles.json
  finding_store_path: ./var/findings.json
```

```python
from pathlib import Path
from sensegnat.api.service import SenseGNATService
from sensegnat.config.settings import load_settings
from sensegnat.ingestion.csv_adapter import CsvEventAdapter

settings = load_settings(Path("sensegnat.yaml"))
service = SenseGNATService(
    adapter=CsvEventAdapter(Path("events.csv")),
    settings=settings,
)
service.run_once()
```

The default paths — used when the `storage` block is absent — are
`./var/profiles.json` and `./var/findings.json`.

---

## What the JSON files look like on disk

### profiles.json

The profile store is a JSON object keyed by `subject_id`:

```json
{
  "alice": {
    "profile_id": "profile-alice",
    "subject_id": "alice",
    "peer_group": "engineering",
    "common_destinations": [
      "203.0.113.10",
      "10.0.0.1",
      "198.51.100.44"
    ],
    "common_ports": [22, 80, 443, 8080],
    "common_protocols": ["tcp"]
  },
  "bob": {
    "profile_id": "profile-bob",
    "subject_id": "bob",
    "peer_group": "engineering",
    "common_destinations": [
      "203.0.113.10",
      "10.0.0.1"
    ],
    "common_ports": [22, 443],
    "common_protocols": ["tcp"]
  }
}
```

`frozenset` values are serialized as JSON arrays. On reload they are
reconstructed as `frozenset` objects. The ordering inside the arrays is not
guaranteed.

### findings.json

The finding store is a JSON array, newest findings appended to the end:

```json
[
  {
    "finding_id": "f8e7d6c5-b4a3-2190-fedc-ba0987654321",
    "finding_type": "rare-destination",
    "seen_at": "2026-04-21T14:29:58.123456+00:00",
    "subject_id": "alice",
    "severity": "medium",
    "score": 0.65,
    "summary": "alice contacted a rare destination 198.51.100.44",
    "evidence": {
      "destination": "198.51.100.44",
      "port": "443",
      "protocol": "tcp"
    }
  }
]
```

Both files are written with `indent=2` and are human-readable.

---

## How profile accumulation works across restarts

`put_many` does not overwrite existing profiles — it merges them:

```python
# JsonProfileStore.put_many (same logic as InMemoryProfileStore)
for subject_id, incoming in profiles.items():
    existing = self._profiles.get(subject_id)
    self._profiles[subject_id] = existing.merge(incoming) if existing else incoming
```

`BehaviorProfile.merge` unions all three observation sets:

```python
def merge(self, incoming: BehaviorProfile) -> BehaviorProfile:
    return BehaviorProfile(
        profile_id=self.profile_id,
        subject_id=self.subject_id,
        peer_group=incoming.peer_group,               # incoming peer_group wins
        common_destinations=self.common_destinations | incoming.common_destinations,
        common_ports=self.common_ports | incoming.common_ports,
        common_protocols=self.common_protocols | incoming.common_protocols,
    )
```

The consequence is that the baseline only grows — observations are never
forgotten when the process restarts. For example:

| Run | Events | alice's profile after `put_many` |
|---|---|---|
| 1 | `10.0.0.1:443` | `{10.0.0.1}` |
| 2 | `10.0.0.2:443` | `{10.0.0.1, 10.0.0.2}` |
| 3 | `10.0.0.1:443` | `{10.0.0.1, 10.0.0.2}` (no rarity finding) |

After run 2, `10.0.0.1` remains in alice's profile even though it was not
observed in run 2's event batch. This is the correct behavior: the profile
represents the cumulative baseline, not just the most recent window.

If you need to reset a subject's baseline — for example, after a role change
— delete their entry from `profiles.json` directly or replace the file with a
fresh one.

---

## When to use each store

**Use `InMemoryProfileStore` / `InMemoryFindingStore` when:**

- Running tests. In-memory stores are faster and leave no files behind.
- Running a one-shot analysis where you don't need the baseline to persist.
- Prototyping a new detector and you want a clean slate on every run.

```python
# Tests always use in-memory stores (no settings arg)
service = SenseGNATService(adapter=adapter)
assert isinstance(service.profile_store, InMemoryProfileStore)
```

**Use `JsonProfileStore` / `JsonFindingStore` when:**

- Running repeated cron-style jobs where the baseline must accumulate across
  runs.
- You want an audit trail of all emitted findings.
- You need to inspect or edit baselines outside the process (the JSON files
  are human-readable).

---

## Inspecting the stores from Python

Read back everything stored so far without running a full pipeline:

```python
from pathlib import Path
from sensegnat.storage.json_store import JsonFindingStore, JsonProfileStore

profile_store = JsonProfileStore(Path("./var/profiles.json"))
for subject_id, profile in profile_store._profiles.items():
    print(subject_id, len(profile.common_destinations), "destinations")

finding_store = JsonFindingStore(Path("./var/findings.json"))
for finding in finding_store.list_all():
    print(finding.seen_at, finding.subject_id, finding.finding_type, finding.severity)
```

`JsonProfileStore._profiles` is a dict keyed by `subject_id`. The public API
(`get`, `put_many`) is sufficient for most use cases; `_profiles` is available
for inspection but should not be mutated directly.

---

## Path configuration notes

- Paths are `pathlib.Path` objects. Relative paths are resolved from the
  current working directory at the time `run_once()` first writes a file.
- Parent directories are created automatically (`mkdir(parents=True,
  exist_ok=True)`) on first write.
- If the path already exists at startup, `JsonProfileStore` loads it
  immediately in `__init__`. Profile data is available for the first
  `run_once()` call without any extra step.
- The stores write on every `put_many` / `add` call. For high-frequency runs,
  consider whether write amplification is acceptable or whether you need a
  batching layer.
