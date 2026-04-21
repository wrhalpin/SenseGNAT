# Tutorial 2: Write a Custom Adapter

In this tutorial you will write a new `EventAdapter` from scratch that reads
network flow records from a JSON-lines log file. By the end you will have:

- A working `JsonLinesAdapter` class that you can use with any `.jsonl` file.
- A sample log file with realistic-looking records.
- SenseGNAT wired up to your adapter and producing findings.
- A two-run exercise that fires a `rare-destination` finding from your own data.

This tutorial builds on [Tutorial 1](01-getting-started.md). You should
already have SenseGNAT installed (`pip install -e .`) and have run the
built-in example at least once.

---

## What an adapter does

SenseGNAT's detection pipeline starts with an `EventAdapter`. Its only job
is to yield `NormalizedNetworkEvent` objects — it does not care where the
data comes from. The rest of the pipeline (profiler, detectors, connector)
never touches raw log files. This separation means you can add support for
any log source — syslog, a REST API, a Kafka topic, a database query — by
writing one class.

The abstract base class lives in `sensegnat/ingestion/base.py`:

```python
from abc import ABC, abstractmethod
from collections.abc import Iterable
from sensegnat.models.events import NormalizedNetworkEvent

class EventAdapter(ABC):
    @abstractmethod
    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        raise NotImplementedError
```

One method, one responsibility: given a source, produce a sequence of
normalized events. The rest is up to you.

---

## The event model

Every event you yield must be a `NormalizedNetworkEvent`. It is a frozen
dataclass defined in `sensegnat/models/events.py`:

```python
@dataclass(frozen=True)
class NormalizedNetworkEvent:
    event_id: str            # unique identifier for this log line
    seen_at: datetime        # timezone-aware timestamp
    source_host: str         # originating host name or IP
    source_user: str | None  # user identity, or None if not available
    destination: str         # destination IP or hostname
    destination_port: int    # destination TCP/UDP port
    protocol: str            # "tcp", "udp", "icmp", etc.
    bytes_out: int = 0       # bytes sent from source to destination
    bytes_in: int = 0        # bytes received from destination
```

A few important details:

- `seen_at` must be **timezone-aware**. If your source timestamps are naive
  UTC, attach `timezone.utc` with `datetime.replace(tzinfo=timezone.utc)`.
- `source_user` is optional. When it is `None`, SenseGNAT uses
  `source_host` as the subject identity for profiling and finding keys.
- `event_id` must be unique within a run. If your log format does not
  provide one, generate a UUID with `str(uuid4())`.
- `frozen=True` means you cannot modify an event after creation. Construct
  it once, completely.

---

## Step 1 — Choose a log format

You are going to parse **JSON-lines** (`.jsonl`) files. Each line is a
self-contained JSON object representing one network flow. This format is
common in modern observability stacks (Vector, Fluent Bit, Elastic Beats).

Here is the schema you will support:

```json
{
  "id": "unique-string",
  "ts": "2026-04-21T09:00:00Z",
  "src_host": "workstation-7",
  "src_user": "bob",
  "dst_ip": "203.0.113.55",
  "dst_port": 443,
  "proto": "tcp",
  "sent_bytes": 4096,
  "recv_bytes": 18200
}
```

All fields except `src_user` are required in every record. `src_user` may
be absent or `null`.

---

## Step 2 — Create the sample data file

Create a directory for your experiment:

```bash
mkdir -p ~/sensegnat-demo
```

Create the sample log file at `~/sensegnat-demo/flows.jsonl`. Each line is
one JSON object. Copy this exactly:

```jsonl
{"id": "flow-001", "ts": "2026-04-21T08:00:00Z", "src_host": "workstation-7", "src_user": "bob", "dst_ip": "203.0.113.55", "dst_port": 443, "proto": "tcp", "sent_bytes": 4096, "recv_bytes": 18200}
{"id": "flow-002", "ts": "2026-04-21T08:01:15Z", "src_host": "workstation-7", "src_user": "bob", "dst_ip": "203.0.113.55", "dst_port": 443, "proto": "tcp", "sent_bytes": 512, "recv_bytes": 900}
{"id": "flow-003", "ts": "2026-04-21T08:02:30Z", "src_host": "workstation-7", "src_user": "bob", "dst_ip": "198.51.100.1", "dst_port": 80, "proto": "tcp", "sent_bytes": 256, "recv_bytes": 4400}
```

These three flows establish `bob`'s baseline: two connections to
`203.0.113.55:443` and one to `198.51.100.1:80`. You will use them in
the first run to build his profile.

Create a second file at `~/sensegnat-demo/flows2.jsonl` for the second run:

```jsonl
{"id": "flow-004", "ts": "2026-04-21T09:00:00Z", "src_host": "workstation-7", "src_user": "bob", "dst_ip": "203.0.113.55", "dst_port": 443, "proto": "tcp", "sent_bytes": 1024, "recv_bytes": 500}
{"id": "flow-005", "ts": "2026-04-21T09:01:00Z", "src_host": "workstation-7", "src_user": "bob", "dst_ip": "192.0.2.200", "dst_port": 8443, "proto": "tcp", "sent_bytes": 12288, "recv_bytes": 300}
```

Flow `flow-004` revisits `203.0.113.55` — already in `bob`'s profile, so
no finding. Flow `flow-005` goes to `192.0.2.200` — a destination `bob`
has never been seen at. That will trigger a `rare-destination` finding.

---

## Step 3 — Write the adapter

Create `~/sensegnat-demo/my_adapter.py` with the following content:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent


class JsonLinesAdapter(EventAdapter):
    """Reads NormalizedNetworkEvent records from a JSON-lines (.jsonl) file.

    Expected record schema:
        {
            "id":         str,            # unique flow identifier
            "ts":         str,            # ISO 8601 timestamp (UTC assumed)
            "src_host":   str,            # originating host
            "src_user":   str | null,     # optional user identity
            "dst_ip":     str,            # destination IP or hostname
            "dst_port":   int,            # destination port
            "proto":      str,            # transport protocol
            "sent_bytes": int,            # bytes sent (optional, default 0)
            "recv_bytes": int             # bytes received (optional, default 0)
        }
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        with self._path.open() as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                yield self._parse_record(record, lineno)

    @staticmethod
    def _parse_record(record: dict, lineno: int) -> NormalizedNetworkEvent:
        # Parse the timestamp. fromisoformat handles "2026-04-21T08:00:00Z"
        # in Python 3.11+. Older Pythons need the Z replaced with +00:00.
        raw_ts = record["ts"].replace("Z", "+00:00")
        seen_at = datetime.fromisoformat(raw_ts)
        if seen_at.tzinfo is None:
            seen_at = seen_at.replace(tzinfo=timezone.utc)

        # source_user may be missing from the dict entirely, or explicitly null
        source_user = record.get("src_user") or None

        return NormalizedNetworkEvent(
            event_id=record.get("id") or str(uuid4()),
            seen_at=seen_at,
            source_host=record["src_host"],
            source_user=source_user,
            destination=record["dst_ip"],
            destination_port=int(record["dst_port"]),
            protocol=record["proto"].lower(),
            bytes_out=int(record.get("sent_bytes") or 0),
            bytes_in=int(record.get("recv_bytes") or 0),
        )
```

Walk through the key decisions in `_parse_record`:

- **Timestamp parsing.** Python 3.11's `datetime.fromisoformat` accepts the
  `Z` suffix, but replacing it with `+00:00` is a safe habit that also works
  on 3.10. Attaching `tzinfo=timezone.utc` when the result is naive ensures
  SenseGNAT always receives timezone-aware datetimes — required by the model.
- **`source_user` normalisation.** `record.get("src_user") or None` handles
  three cases: the key is absent, the value is `null` (Python `None`), or the
  value is an empty string. All three become `None`.
- **`event_id` fallback.** If the record has no `id`, a fresh UUID is generated.
  IDs only need to be unique within a single `fetch_events()` call.
- **`protocol.lower()`.** The `ProfileBuilder` stores protocols in a frozenset
  for comparison. Lower-casing is a safety measure in case your source uses
  `"TCP"` or `"Tcp"`.

---

## Step 4 — Wire the adapter into SenseGNATService

Create `~/sensegnat-demo/run_demo.py`:

```python
from __future__ import annotations

from pathlib import Path

from sensegnat.api.service import SenseGNATService
from my_adapter import JsonLinesAdapter


FLOWS_RUN1 = Path("~/sensegnat-demo/flows.jsonl").expanduser()
FLOWS_RUN2 = Path("~/sensegnat-demo/flows2.jsonl").expanduser()


def print_records(records: list[dict]) -> None:
    if not records:
        print("  (no records published)")
        return
    for r in records:
        rtype = r.get("type")
        if rtype == "indicator":
            print(f"  [indicator] {r['x_gnat_signature']}")
            print(f"    subject  : {r['x_sensegnat_subject_id']}")
            print(f"    severity : {r['x_sensegnat_severity']}")
            print(f"    score    : {r['x_sensegnat_score']}")
            print(f"    summary  : {r['x_sensegnat_summary']}")
            print(f"    evidence : {r['x_sensegnat_evidence']}")
        elif rtype == "note":
            print(f"  [note]      {r['content']}")
        print()


# --- Run 1: build bob's profile from flows.jsonl ---
print("=== Run 1 — building baseline ===")
service = SenseGNATService(adapter=JsonLinesAdapter(FLOWS_RUN1))
records = service.run_once()
print_records(records)

# --- Run 2: feed flows2.jsonl — flow-005 will fire a finding ---
print("=== Run 2 — detecting anomaly ===")
service.adapter = JsonLinesAdapter(FLOWS_RUN2)
records = service.run_once()
print_records(records)
```

Notice that you reuse the same `service` instance across both runs. The
`InMemoryProfileStore` inside `service` accumulates profiles between runs,
which is exactly what you need to simulate a real multi-batch deployment.

---

## Step 5 — Run it

```bash
cd ~/sensegnat-demo
python run_demo.py
```

Expected output:

```
=== Run 1 — building baseline ===
  (no records published)

=== Run 2 — detecting anomaly ===
  [indicator] rare-destination
    subject  : bob
    severity : medium
    score    : 0.65
    summary  : bob contacted a rare destination 192.0.2.200
    evidence : {'destination': '192.0.2.200', 'port': '8443', 'protocol': 'tcp'}

  [note]      bob: 1 finding(s) — rare-destination. Severity: medium, peak score: 0.65.
```

Run 1 published nothing — `bob` had no prior profile, so
`RareDestinationDetector` returned `None` for all three flows. The profiler
recorded `203.0.113.55` and `198.51.100.1` as `bob`'s known destinations.

Run 2 published two records:

- `flow-004` visits `203.0.113.55`, which is in the profile. No finding.
- `flow-005` visits `192.0.2.200`, which is **not** in the profile. Finding
  fires.
- `NarrativeBuilder` rolled that one finding into a `note`.

---

## Step 6 — Handle errors robustly

The adapter above will raise a `json.JSONDecodeError` if any line is
malformed, and a `KeyError` if a required field is missing. For a production
adapter you should handle these explicitly:

```python
def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
    with self._path.open() as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{self._path}:{lineno}: invalid JSON — {exc}"
                ) from exc
            try:
                yield self._parse_record(record, lineno)
            except KeyError as exc:
                raise ValueError(
                    f"{self._path}:{lineno}: missing required field {exc}"
                ) from exc
```

This follows SenseGNAT's convention: **no bare `except`**. Surface errors
with context — file name and line number — so the caller knows exactly where
to look.

---

## Step 7 — Extend the adapter

### Supporting multiple files

If your log rotation produces one file per hour, accept a list of paths:

```python
class JsonLinesAdapter(EventAdapter):
    def __init__(self, paths: list[Path]) -> None:
        self._paths = [Path(p) for p in paths]

    def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
        for path in self._paths:
            with path.open() as fh:
                for lineno, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    yield self._parse_record(json.loads(line), lineno)
```

Wire it in:

```python
from pathlib import Path
service = SenseGNATService(
    adapter=JsonLinesAdapter(sorted(Path("/var/log/flows").glob("*.jsonl")))
)
```

### Supporting a different timestamp format

If your source emits Unix epoch floats instead of ISO 8601 strings, swap
the timestamp parsing line:

```python
seen_at = datetime.fromtimestamp(float(record["ts"]), tz=timezone.utc)
```

The existing `CsvEventAdapter` (`sensegnat/ingestion/csv_adapter.py`) uses
the same pattern — try ISO 8601 first and fall back to epoch float:

```python
try:
    seen_at = datetime.fromisoformat(raw_ts).replace(tzinfo=timezone.utc)
except ValueError:
    seen_at = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
```

### Adding host-only events (no user field)

If your log source does not record user identities, set `source_user=None`
consistently. SenseGNAT will then use `source_host` as the subject ID, and
profiles will be per-host rather than per-user.

---

## Step 8 — Add a third run to watch the profile grow

Add a third run to `run_demo.py` to see how the profile accumulates:

```python
import json
from pathlib import Path

FLOWS_RUN3 = Path("~/sensegnat-demo/flows3.jsonl").expanduser()

# Write flows3.jsonl inline for the demo
FLOWS_RUN3.write_text(
    '{"id": "flow-006", "ts": "2026-04-21T10:00:00Z", '
    '"src_host": "workstation-7", "src_user": "bob", '
    '"dst_ip": "192.0.2.200", "dst_port": 8443, "proto": "tcp", '
    '"sent_bytes": 500, "recv_bytes": 100}\n'
)

print("=== Run 3 — same destination as run 2 finding ===")
service.adapter = JsonLinesAdapter(FLOWS_RUN3)
records = service.run_once()
print_records(records)
```

Expected output for run 3:

```
=== Run 3 — same destination as run 2 finding ===
  (no records published)
```

`192.0.2.200` was added to `bob`'s profile at the end of run 2
(`put_many` merges via `BehaviorProfile.merge()`). On run 3 it is already
known, so no finding fires. This is how SenseGNAT learns: each run that
does not produce a finding expands the baseline so that the same connection
is never flagged twice.

---

## Checklist: what makes a good adapter

Before you use your adapter in production, verify:

- [ ] `fetch_events()` is a generator or returns a list — both satisfy
  `Iterable[NormalizedNetworkEvent]`.
- [ ] Every `seen_at` is timezone-aware (`seen_at.tzinfo is not None`).
- [ ] `source_user` is `None`, not `""`, when the field is absent.
- [ ] `protocol` is lower-case.
- [ ] `event_id` values are unique within a single call.
- [ ] Malformed records raise an informative exception, not a bare `except`.
- [ ] The adapter does not hold open file handles or database connections
  between calls to `fetch_events()`.

---

## What to read next

- **`sensegnat/ingestion/csv_adapter.py`** — the `CsvEventAdapter` for named-
  column CSV files. Compare its `_parse_row` to your `_parse_record`.
- **`sensegnat/ingestion/zeek_conn_adapter.py`** — the `ZeekConnLogAdapter`
  for Zeek `conn.log` TSV files with a dynamic `#fields` header. A good
  example of handling a more complex format.
- **`sensegnat/ingestion/suricata_eve_adapter.py`** — the
  `SuricataEveAdapter` for Suricata EVE JSON flow and alert records. Shows
  how to filter record types within `fetch_events()`.
- **Tutorial 1** — [Getting Started](01-getting-started.md) — covers the
  full data flow from adapter through to published STIX records if you have
  not read it yet.
- **Adding a new detector** — see the `CLAUDE.md` guide in the repo root for
  the four-step recipe.
