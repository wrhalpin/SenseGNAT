# Tutorial 1: Getting Started with SenseGNAT

In this tutorial you will install SenseGNAT, run the built-in example, read
and understand the output, and then trigger your first real finding by feeding
the system two batches of events for the same subject — the second batch
visiting a destination the subject has never been seen at before.

By the end you will:

- Have SenseGNAT installed and working.
- Know what a "published record" is, what its fields mean, and how they map
  to the STIX 2.1 standard.
- Have watched a `rare-destination` finding fire and produced a narrative
  record.
- Have a mental model of the data flow that connects every component.

This tutorial does **not** cover writing your own adapter, loading a YAML
policy file, or connecting to a running GNAT instance. Those come later.

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.11 or later |
| pip | any recent version |
| Git | to clone the repo |

You do not need a running GNAT server. SenseGNAT operates in **record-only
mode** by default — it builds STIX objects and returns them as Python dicts
without making any network calls.

---

## Step 1 — Install

Clone the repository and install it in editable mode from the project root.
Editable mode is required because the package lives at the root, not under
`src/`.

```bash
git clone <repo-url> SenseGNAT
cd SenseGNAT
pip install -e .
```

Verify the installation:

```bash
python -c "import sensegnat; print('ok')"
```

You should see `ok`. If you see an `ImportError`, make sure you ran
`pip install -e .` from the project root (the directory that contains
`pyproject.toml`).

---

## Step 2 — Run the built-in example

The repository ships with a runnable script at `examples/run_phase_a.py`.
Run it now:

```bash
python examples/run_phase_a.py
```

You will see output like this (UUIDs will differ every run):

```
{'published_records': []}
```

An empty list is correct on the first run. Here is why: the
`RareDestinationDetector` only fires when a subject has an **existing**
profile and then visits a destination that is not in that profile. On the
very first run there is no prior profile, so no finding is raised. The
profile is built and stored during the run, ready for the next one.

Run it a second time:

```bash
python examples/run_phase_a.py
```

This time the output is a Python dict with at least one published record.
The exact content will look something like this (formatted here for
readability):

```python
{
  'published_records': [
    {
      'type': 'indicator',
      'spec_version': '2.1',
      'id': 'indicator--3f2a1b4c-...',
      'created': '2026-04-21T10:00:00.123456+00:00',
      'modified': '2026-04-21T10:00:00.123456+00:00',
      'name': 'sensegnat:rare-destination:alice',
      'pattern': "[ipv4-addr:value = '198.51.100.44']",
      'pattern_type': 'stix',
      'valid_from': '2026-04-21T10:00:00.123456+00:00',
      'indicator_types': ['anomalous-activity'],
      'confidence': 75,
      'x_gnat_sensor_type': 'ids_alert',
      'x_gnat_sensor_id': 'sensegnat',
      'x_gnat_signature': 'rare-destination',
      'x_gnat_tags': ['alice'],
      'x_gnat_tlp': 'white',
      'x_sensegnat_finding_id': 'e7b9f2a1-...',
      'x_sensegnat_score': 0.65,
      'x_sensegnat_severity': 'medium',
      'x_sensegnat_summary': 'alice contacted a rare destination 198.51.100.44',
      'x_sensegnat_evidence': {
        'destination': '198.51.100.44',
        'port': '443',
        'protocol': 'tcp'
      },
      'x_sensegnat_subject_id': 'alice'
    },
    {
      'type': 'note',
      ...
      'content': 'alice: 1 finding(s) — rare-destination. Severity: medium, peak score: 0.65.',
      'x_sensegnat_subject_id': 'alice',
      'x_sensegnat_finding_count': 1,
      'x_sensegnat_severity': 'medium',
      'x_sensegnat_score': 0.65,
      'x_sensegnat_finding_types': ['rare-destination']
    }
  ]
}
```

Wait — on the second run the example's `SampleEventAdapter` still sends
`198.51.100.44`. That destination was already recorded in the profile from
run one, so `rare-destination` should **not** fire again. But the
`examples/sensegnat.example.yaml` config points storage at
`./var/profiles.json` — a file that persists across runs. On run two the
profile already contains `198.51.100.44`, so no finding fires.

> **If you see an empty list on run two:** delete `var/profiles.json` (if it
> exists) and run again. The first run creates the profile; the second run
> finds nothing new because the sample adapter sends the same destination
> both times. Jump to the hands-on exercise below to see a finding fire.

---

## Step 3 — Understanding the output

Each published record is a **STIX 2.1** object. SenseGNAT produces two kinds:

### `indicator` records — one per finding

An `indicator` record represents a single anomaly detection event. The
standard STIX fields tell downstream consumers what kind of object this is
and how to match it against network data. The `x_gnat_*` and
`x_sensegnat_*` fields carry SenseGNAT-specific metadata.

| Field | What it contains |
|-------|-----------------|
| `type` | Always `"indicator"` for findings |
| `pattern` | A STIX pattern expression. For a destination-based finding this is `[ipv4-addr:value = '<ip>']` |
| `x_gnat_signature` | The detector that fired — `"rare-destination"`, `"peer-deviation"`, `"policy-violation"`, or `"time-window-drift"` |
| `x_sensegnat_severity` | `"low"`, `"medium"`, `"high"`, or `"critical"` |
| `x_sensegnat_score` | A float between 0.0 and 1.0. Higher means more anomalous. `RareDestinationDetector` always returns `0.65` |
| `x_sensegnat_summary` | A human-readable sentence describing what happened — safe to surface in a UI or alert |
| `x_sensegnat_evidence` | A dict of key-value strings that explain *why* the finding fired (destination, port, protocol, etc.) |
| `x_sensegnat_subject_id` | The identity that triggered the finding — the `source_user` if present, otherwise `source_host` |
| `x_gnat_tags` | List containing the subject ID — used for tag-based filtering in GNAT |
| `confidence` | STIX confidence score (0–100). Defaults to `75` |

### `note` records — one per subject per run

After all findings for a subject are gathered, SenseGNAT's
`NarrativeBuilder` rolls them into a single `note` record. The note
provides a summary sentence, a severity rollup (highest across all
findings), and a peak score. If a subject generates no findings in a run,
no note is emitted.

| Field | What it contains |
|-------|-----------------|
| `type` | Always `"note"` for narratives |
| `content` | Human-readable summary: `"alice: 1 finding(s) — rare-destination. Severity: medium, peak score: 0.65."` |
| `x_sensegnat_finding_count` | Total findings for this subject in this run |
| `x_sensegnat_finding_types` | List of finding type strings, most frequent first |
| `x_sensegnat_severity` | Highest severity across all findings |
| `x_sensegnat_score` | Highest score across all findings |

---

## Step 4 — Hands-on exercise: trigger a finding yourself

The built-in example sends the same event every run, which makes it hard to
observe a finding firing deliberately. In this exercise you will use a
minimal inline adapter to control exactly what events are sent on each run.

Create a new file called `two_runs.py` anywhere convenient (your home
directory is fine) and paste the following:

```python
from datetime import datetime, timezone

from sensegnat.api.service import SenseGNATService
from sensegnat.ingestion.base import EventAdapter
from sensegnat.models.events import NormalizedNetworkEvent


class TwoRunAdapter(EventAdapter):
    """A minimal adapter that returns whatever event list you hand it."""

    def __init__(self, events):
        self._events = events

    def fetch_events(self):
        return self._events


def make_event(eid, dest):
    return NormalizedNetworkEvent(
        event_id=eid,
        seen_at=datetime.now(timezone.utc),
        source_host="laptop-01",
        source_user="alice",
        destination=dest,
        destination_port=443,
        protocol="tcp",
    )


# --- Run 1: build alice's profile with a single known destination ---
service = SenseGNATService(adapter=TwoRunAdapter([make_event("e1", "203.0.113.10")]))
run1 = service.run_once()
print(f"Run 1: {len(run1)} record(s) published")

# --- Run 2: alice visits a destination she has never been seen at ---
service.adapter = TwoRunAdapter([make_event("e2", "198.51.100.99")])
records = service.run_once()
print(f"Run 2: {len(records)} record(s) published")

for r in records:
    print()
    print(f"  type             : {r.get('type')}")
    print(f"  x_gnat_signature : {r.get('x_gnat_signature')}")
    print(f"  x_sensegnat_severity : {r.get('x_sensegnat_severity')}")
    print(f"  x_sensegnat_score    : {r.get('x_sensegnat_score')}")
    print(f"  x_sensegnat_summary  : {r.get('x_sensegnat_summary')}")
    if r.get("content"):
        print(f"  content          : {r.get('content')}")
```

Run it:

```bash
python two_runs.py
```

Expected output:

```
Run 1: 0 record(s) published

Run 2: 2 record(s) published

  type             : indicator
  x_gnat_signature : rare-destination
  x_sensegnat_severity : medium
  x_sensegnat_score    : 0.65
  x_sensegnat_summary  : alice contacted a rare destination 198.51.100.99

  type             : note
  x_gnat_signature : None
  x_sensegnat_severity : medium
  x_sensegnat_score    : 0.65
  x_sensegnat_summary  : None
  content          : alice: 1 finding(s) — rare-destination. Severity: medium, peak score: 0.65.
```

### What just happened

**Run 1** sent `e1` with destination `203.0.113.10`. There was no prior
profile for `alice`, so `RareDestinationDetector` returned `None`. The
`ProfileBuilder` built `alice`'s first profile and `InMemoryProfileStore`
saved it. Zero records published.

**Run 2** sent `e2` with destination `198.51.100.99`. This time `alice`
**does** have a profile — the one built in run one — and `198.51.100.99`
is not in it. `RareDestinationDetector` fired, producing a `Finding`.
`GNATConnector.to_record()` converted that `Finding` into the STIX
`indicator` dict. `NarrativeBuilder` then rolled that single finding into a
`Narrative`, which `GNATConnector.narrative_to_record()` converted into the
STIX `note` dict. Two records published.

### Things to try

- Change `destination_port` in run 2 to `22` (SSH). You will still get a
  `rare-destination` finding because the detector keys on destination IP,
  not port.
- Add a third run with the **same** destination as run 2. You should get
  **no** finding — the destination is now part of `alice`'s profile.
- Add two events in run 2, each to a different novel destination. You will
  get two `indicator` records but still only one `note`.

---

## Step 5 — What happened under the hood

Here is the full data flow through `SenseGNATService.run_once()`:

```
TwoRunAdapter.fetch_events()
    │
    │  returns a list of NormalizedNetworkEvent objects
    ▼
ProfileBuilder.build(events)
    │
    │  groups events by subject_id (source_user if set, else source_host)
    │  builds a BehaviorProfile per subject:
    │    common_destinations = frozenset of all destinations in this batch
    │    common_ports        = frozenset of all ports
    │    common_protocols    = frozenset of all protocols
    ▼
RareDestinationDetector.detect(event, existing_profile)
    │
    │  existing_profile is the profile from BEFORE this run (the snapshot)
    │  if existing_profile is None  → no finding (first-ever run)
    │  if destination in profile    → no finding
    │  otherwise                    → Finding(finding_type="rare-destination", ...)
    ▼
InMemoryFindingStore.add(finding)
GNATConnector.to_record(finding)   → STIX indicator dict
    │
    ▼
NarrativeBuilder.build(subject_id, findings)
    │
    │  rolls all findings for alice in this run into one Narrative
    │  severity = highest across all findings
    │  score    = peak score across all findings
    ▼
GNATConnector.narrative_to_record(narrative)   → STIX note dict
    │
    ▼
InMemoryProfileStore.put_many(new_profiles)
    │
    │  merges new profile into existing via BehaviorProfile.merge()
    │  union of destination/port/protocol sets — knowledge accumulates
    ▼
run_once() returns [indicator_dict, note_dict]
```

Three important things to notice:

1. **The detector sees the pre-run profile snapshot**, not the profile
   being built during this run. This prevents the same event from both
   building a profile and immediately matching it — the first-run no-op
   is intentional.

2. **Profiles accumulate across runs.** `BehaviorProfile.merge()` unions
   the observation sets, so the longer SenseGNAT runs, the richer the
   baseline becomes, and the fewer false positives you will see for
   legitimately new-but-recurring destinations.

3. **Every finding is explainable.** The `evidence` dict in each
   `Finding` records exactly which fields caused the detector to fire.
   `x_sensegnat_summary` is always a human-readable sentence. There is no
   opaque ML score — you can always trace why an indicator was raised.

---

## Step 6 — The internal data structures

You have now seen the published output. Here is a brief look at the internal
objects that flow through the pipeline.

### `NormalizedNetworkEvent`

This is the input to every other component. It is a frozen dataclass —
once created, it cannot be modified. The fields that matter most for
detection are:

```python
@dataclass(frozen=True)
class NormalizedNetworkEvent:
    event_id: str            # unique identifier for this log line
    seen_at: datetime        # timezone-aware; required
    source_host: str         # originating host
    source_user: str | None  # user identity — used as subject ID when present
    destination: str         # destination IP or hostname
    destination_port: int
    protocol: str
    bytes_out: int = 0
    bytes_in: int = 0
```

`source_user` drives the subject identity. When it is set, all profiles and
findings are keyed to the user name. When it is `None`, `source_host` is
used. In the hands-on exercise above you set `source_user="alice"`, so all
profile and finding keys read `"alice"`.

### `BehaviorProfile`

The profiler builds one `BehaviorProfile` per subject per run. A profile is
a lightweight summary of observed behaviour:

```python
@dataclass(frozen=True)
class BehaviorProfile:
    profile_id: str
    subject_id: str
    peer_group: str | None
    common_destinations: FrozenSet[str]
    common_ports: FrozenSet[int]
    common_protocols: FrozenSet[str]
```

`common_destinations` is the set the `RareDestinationDetector` checks
against. When the profile is stored, `BehaviorProfile.merge()` unions the
new destinations into whatever was already stored, so the set only ever
grows.

### `Finding`

Every detector returns either `None` or a `Finding`:

```python
@dataclass(frozen=True)
class Finding:
    finding_id: str       # UUID
    finding_type: str     # "rare-destination", "peer-deviation", etc.
    seen_at: datetime
    subject_id: str
    severity: str         # "low", "medium", "high", "critical"
    score: float          # 0.0–1.0
    summary: str          # human-readable sentence
    evidence: dict[str, str]  # key-value context for the finding
```

`GNATConnector.to_record()` maps every field of a `Finding` directly to
one of the STIX `x_sensegnat_*` extension properties you saw in the output.
There is no lossy transformation — every piece of information is preserved.

---

## Next steps

- **Tutorial 2** — [Write a Custom Adapter](02-write-a-custom-adapter.md):
  learn how to ingest your own log format by subclassing `EventAdapter`.
- **Configuration** — edit `examples/sensegnat.example.yaml` to enable
  disk persistence and a policy file, then re-run the example to see
  `PolicyViolationDetector` fire.
- **Detectors** — read `sensegnat/detection/` to see how
  `PeerDeviationDetector` and `TimeWindowDriftDetector` work; both follow
  the same `detect(event, profile) -> Finding | None` pattern as
  `RareDestinationDetector`.
