# SenseGNAT — Claude Code Guide

## What this project is

SenseGNAT is a standalone behavior analytics capability that integrates into GNAT via a connector contract. It builds per-entity behavioral baselines from normalized network telemetry, runs explainable detectors against those baselines, and emits structured findings back into GNAT.

Tagline: "Behavior is the signal."

See `docs/archtiecture/adrs/` for the five decisions that shaped the design.

---

## Running the project

Install in editable mode first (required; the package lives at the project root, not under `src/`):

```bash
pip install -e .
```

Run the Phase A example:

```bash
python examples/run_phase_a.py
```

Run tests:

```bash
pytest
```

> **Known issue:** `pyproject.toml` currently sets `pythonpath = ["src"]` which points nowhere. After `pip install -e .` this doesn't matter, but the setting should be corrected to `pythonpath = ["."]` or removed.

---

## Package layout

```
sensegnat/
  models/       # Frozen dataclasses — the data contracts (events, entities, findings)
  ingestion/    # EventAdapter ABC + concrete source adapters
  behavior/     # ProfileBuilder — aggregates events into BehaviorProfile objects
  detection/    # Explainable detectors (RareDestinationDetector is the only one so far)
  storage/      # InMemoryProfileStore / InMemoryFindingStore (disk persistence TODO)
  connectors/   # GNATConnector — converts Finding → GNAT record dict
  config/       # Pydantic settings models (no YAML loader yet)
  api/          # SenseGNATService — the main orchestrator
  common/       # Reserved for shared utilities (currently empty)

tests/          # pytest suite (project root, not inside the package)
examples/       # Runnable scripts and config templates
docs/           # ADRs, architecture diagrams, branding
```

---

## Core data flow

```
EventAdapter.fetch_events()
  → ProfileBuilder.build()        # builds BehaviorProfile per subject
  → RareDestinationDetector.detect()  # compares event to existing profile
  → InMemoryFindingStore.add()
  → GNATConnector.to_record()     # converts Finding to GNAT-compatible dict
```

`SenseGNATService.run_once()` (`sensegnat/api/service.py`) wires all of this together.

---

## Conventions

- **Models are frozen dataclasses.** `NormalizedNetworkEvent`, `BehaviorProfile`, `Finding` are all `@dataclass(frozen=True)`. Do not use Pydantic for data-plane objects.
- **Configuration uses Pydantic BaseModel.** `SenseGNATSettings` and its sub-models live in `sensegnat/config/settings.py`.
- **New source adapters subclass `EventAdapter`** (`sensegnat/ingestion/base.py`). Implement `fetch_events() -> Iterable[NormalizedNetworkEvent]`.
- **New detectors follow the `RareDestinationDetector` pattern**: take `(event, profile | None)`, return `Finding | None`. No shared state.
- **All detectors must be explainable.** Every `Finding` needs a human-readable `summary` and a populated `evidence` dict. See ADR-003.
- **`from __future__ import annotations`** at the top of every module.
- **No bare `except`.** Surface errors; don't swallow them silently.

---

## Phase A scope (what's wired up now)

- Single adapter: `SampleEventAdapter` (hardcoded fixture event)
- Single detector: `RareDestinationDetector` — flags destinations absent from a subject's profile
- In-memory stores only — nothing persists across runs
- One passing unit test in `tests/test_rarity.py`

## Not yet implemented (Phase B and beyond)

- YAML config loader — `SenseGNATSettings` models exist but nothing reads `sensegnat.example.yaml` at runtime
- Disk persistence — `StorageSettings` has paths but `InMemoryProfileStore` ignores them
- Additional detectors — peer deviation, time-window drift, policy rule violations (all referenced in ADRs but absent)
- Policy engine — referenced in ADR-002 and the architecture diagram; no code yet
- Risk narrative builder — referenced in the architecture diagram; no code yet
- Real event adapters — Zeek, Suricata, or GNAT telemetry feeds
- `sensegnat.common` — empty; shared utilities belong here when needed

---

## Adding a new detector

1. Create `sensegnat/detection/<name>.py`
2. Define a class with a `detect(event, profile | None) -> Finding | None` method
3. Wire it into `SenseGNATService.__init__` and call it in `run_once()`
4. Add a test in `tests/test_<name>.py`

---

## Architecture decisions

All five ADRs are in `docs/archtiecture/adrs/` (note the typo in the directory name — `archtiecture`):

| ADR | Decision |
|-----|----------|
| 001 | SenseGNAT is standalone, not baked into GNAT core |
| 002 | Baselines are policy-seeded and telemetry-refined |
| 003 | Explainability over opaque ML |
| 004 | Profiles and findings are keyed to canonical entities |
| 005 | Custom behavior objects with STIX interop |
