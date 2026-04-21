# How to add a behavioral detector

This guide shows you how to write a new stateless detector, place it in the
right location, wire it into `SenseGNATService`, and cover it with a test.

---

## When to write a custom detector

Use an existing detector if the signal you need is already modeled:

| Detector | File | Fires when |
|---|---|---|
| `RareDestinationDetector` | `rarity.py` | Destination absent from subject's historical profile |
| `PeerDeviationDetector` | `peer_deviation.py` | Destination or port not seen by any peer-group member |
| `PolicyViolationDetector` | `policy_violation.py` | Destination or port outside policy allow-list |
| `TimeWindowDriftDetector` | `time_window_drift.py` | Novel-destination count expands profile by > threshold% |

Write a new detector when the signal does not fit any of the above — for
example, byte-volume anomalies, unusual protocols, or time-of-day violations.

---

## The detector contract

Every detector is a plain class with a `detect` method. There is no base class
to inherit; the contract is structural.

```python
def detect(
    self,
    event: NormalizedNetworkEvent,
    profile: BehaviorProfile | None,
) -> Finding | None:
    ...
```

Rules:
- **Stateless.** The detector must not store state between calls. All inputs
  arrive as arguments; all outputs are return values.
- **Return `None` when there is nothing to report.** Never raise an exception
  to signal a non-finding.
- **Every `Finding` must have a human-readable `summary` and a populated
  `evidence` dict.** Explainability is not optional (see ADR-003).
- **`profile` may be `None`** if the subject has no history yet. Handle that
  case explicitly.

---

## Data model reference

### `NormalizedNetworkEvent` (frozen dataclass)

```python
event_id: str
seen_at: datetime
source_host: str
source_user: str | None
destination: str
destination_port: int
protocol: str
bytes_out: int   # default 0
bytes_in: int    # default 0
```

The subject identity is `event.source_user or event.source_host`.

### `BehaviorProfile` (frozen dataclass)

```python
profile_id: str
subject_id: str
peer_group: str | None
common_destinations: frozenset[str]
common_ports: frozenset[int]
common_protocols: frozenset[str]
```

### `Finding` (frozen dataclass)

```python
finding_id: str          # unique ID, use str(uuid4())
finding_type: str        # machine-readable label, e.g. "high-byte-volume"
seen_at: datetime        # use utcnow() from sensegnat.common.time_utils
subject_id: str
severity: str            # "low" | "medium" | "high" | "critical"
score: float             # 0.0 – 1.0
summary: str             # one human-readable sentence
evidence: dict[str, str] # key/value pairs that explain the finding
```

---

## Worked example: `HighByteVolumeDetector`

This detector fires when `event.bytes_out` exceeds a configurable threshold.
It is independent of the behavioral profile — profile may be `None` and the
detector fires regardless.

### 1. Create the file

**`sensegnat/detection/high_byte_volume.py`**

```python
from __future__ import annotations

from uuid import uuid4

from sensegnat.common.time_utils import utcnow
from sensegnat.models.entities import BehaviorProfile
from sensegnat.models.events import NormalizedNetworkEvent
from sensegnat.models.findings import Finding

_DEFAULT_THRESHOLD = 10_000_000  # 10 MB


class HighByteVolumeDetector:
    """Flags outbound transfers that exceed a byte-volume threshold.

    Args:
        threshold: bytes_out value above which a finding is emitted.
            Defaults to 10 MB (10_000_000 bytes).
    """

    def __init__(self, threshold: int = _DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold

    def detect(
        self,
        event: NormalizedNetworkEvent,
        profile: BehaviorProfile | None,  # noqa: ARG002 — not used by this detector
    ) -> Finding | None:
        if event.bytes_out <= self._threshold:
            return None

        subject_id = event.source_user or event.source_host
        return Finding(
            finding_id=str(uuid4()),
            finding_type="high-byte-volume",
            seen_at=utcnow(),
            subject_id=subject_id,
            severity="high",
            score=min(round(event.bytes_out / (self._threshold * 10), 2), 1.0),
            summary=(
                f"{subject_id} sent {event.bytes_out:,} bytes to "
                f"{event.destination} (threshold: {self._threshold:,})"
            ),
            evidence={
                "bytes_out": str(event.bytes_out),
                "threshold": str(self._threshold),
                "destination": event.destination,
                "port": str(event.destination_port),
                "protocol": event.protocol,
            },
        )
```

Key choices to note:
- The score is proportional to how far the transfer exceeds the threshold,
  capped at 1.0. Adjust this formula for your use case.
- `profile` is accepted but unused; the type annotation keeps the method
  signature consistent with the rest of the codebase.
- `from __future__ import annotations` is required at the top of every module.

---

### 2. Wire it into `SenseGNATService`

Open `sensegnat/api/service.py` and make two changes.

**Add the import** near the top with the other detector imports:

```python
from sensegnat.detection.high_byte_volume import HighByteVolumeDetector
```

**Instantiate it in `__init__`** alongside the other detectors:

```python
class SenseGNATService:
    def __init__(self, adapter: EventAdapter, settings: SenseGNATSettings | None = None) -> None:
        self.adapter = adapter
        self.profile_builder = ProfileBuilder()
        self.rare_detector = RareDestinationDetector()
        self.peer_detector = PeerDeviationDetector()
        self.policy_violation_detector = PolicyViolationDetector()
        self.drift_detector = TimeWindowDriftDetector()
        self.volume_detector = HighByteVolumeDetector()   # <-- add this
        self.narrative_builder = NarrativeBuilder()
        ...
```

If you want the threshold to be configurable from settings, pass it from your
`SenseGNATSettings` subclass:

```python
self.volume_detector = HighByteVolumeDetector(
    threshold=settings.runtime.high_byte_volume_threshold
)
```

**Call it in `run_once()`** inside the per-event loop, after the existing
per-event detectors:

```python
for event in events:
    subject_id = event.source_user or event.source_host
    existing_profile = existing[subject_id]
    new_profile = profiles.get(subject_id)

    # Rarity
    finding = self.rare_detector.detect(event, existing_profile)
    if finding is not None:
        self.finding_store.add(finding)
        published.append(self.connector.to_record(finding))
        findings_by_subject[subject_id].append(finding)

    # ... peer deviation, policy violation ...

    # High byte volume
    finding = self.volume_detector.detect(event, existing_profile)
    if finding is not None:
        self.finding_store.add(finding)
        published.append(self.connector.to_record(finding))
        findings_by_subject[subject_id].append(finding)
```

The pattern is identical for every per-event detector: call `detect`, check
for `None`, then store and publish.

---

### 3. Write a test

**`tests/test_high_byte_volume.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from sensegnat.detection.high_byte_volume import HighByteVolumeDetector
from sensegnat.models.events import NormalizedNetworkEvent


def _event(bytes_out: int = 0) -> NormalizedNetworkEvent:
    return NormalizedNetworkEvent(
        event_id="evt-test",
        seen_at=datetime.now(timezone.utc),
        source_host="host-1",
        source_user="alice",
        destination="203.0.113.10",
        destination_port=443,
        protocol="tcp",
        bytes_out=bytes_out,
    )


def test_no_finding_below_threshold() -> None:
    detector = HighByteVolumeDetector(threshold=10_000_000)
    assert detector.detect(_event(bytes_out=5_000_000), profile=None) is None


def test_no_finding_at_threshold() -> None:
    detector = HighByteVolumeDetector(threshold=10_000_000)
    assert detector.detect(_event(bytes_out=10_000_000), profile=None) is None


def test_finding_above_threshold() -> None:
    detector = HighByteVolumeDetector(threshold=10_000_000)
    finding = detector.detect(_event(bytes_out=15_000_000), profile=None)
    assert finding is not None
    assert finding.finding_type == "high-byte-volume"
    assert finding.severity == "high"
    assert finding.subject_id == "alice"


def test_finding_evidence_contains_bytes_out() -> None:
    detector = HighByteVolumeDetector(threshold=10_000_000)
    finding = detector.detect(_event(bytes_out=20_000_000), profile=None)
    assert finding is not None
    assert finding.evidence["bytes_out"] == "20000000"
    assert finding.evidence["threshold"] == "10000000"


def test_custom_threshold_respected() -> None:
    detector = HighByteVolumeDetector(threshold=1_000)
    assert detector.detect(_event(bytes_out=500), profile=None) is None
    assert detector.detect(_event(bytes_out=1_001), profile=None) is not None


def test_profile_none_does_not_prevent_finding() -> None:
    detector = HighByteVolumeDetector(threshold=1_000)
    finding = detector.detect(_event(bytes_out=5_000), profile=None)
    assert finding is not None
```

Run with:

```bash
pytest tests/test_high_byte_volume.py -v
```

---

## Checklist

- [ ] File is in `sensegnat/detection/<name>.py`
- [ ] Module starts with `from __future__ import annotations`
- [ ] `detect(event, profile | None) -> Finding | None` signature
- [ ] Returns `None` rather than raising when there is no finding
- [ ] Handles `profile is None` explicitly
- [ ] Every returned `Finding` has a non-empty `summary` and `evidence`
- [ ] Imported and instantiated in `SenseGNATService.__init__`
- [ ] Called and its result processed in `run_once()`
- [ ] Tests in `tests/test_<name>.py` covering the threshold boundary, `None`
      profile, and `evidence` content
