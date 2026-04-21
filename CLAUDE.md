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
  models/       # Frozen dataclasses — the data contracts (events, entities, findings, narratives)
  ingestion/    # EventAdapter ABC + concrete source adapters (SampleEventAdapter, CsvEventAdapter)
  behavior/     # ProfileBuilder — aggregates events into BehaviorProfile objects
  detection/    # Explainable detectors (RareDestinationDetector, PeerDeviationDetector)
  storage/      # InMemoryProfileStore / InMemoryFindingStore + JSON-backed equivalents
  connectors/   # GNATConnector — converts Finding/Narrative → GNAT record dicts
  config/       # Pydantic settings models + load_settings(path) YAML loader
  policy/       # PolicyEngine — loads per-subject/group rules from YAML
  narrative/    # NarrativeBuilder — rolls per-subject findings into a Narrative
  api/          # SenseGNATService — the main orchestrator
  common/       # Shared utilities: to_dict (serialization), utcnow (time)

tests/          # pytest suite (project root, not inside the package)
examples/       # Runnable scripts, config templates, and sample data
docs/           # ADRs, architecture diagrams, branding
```

---

## Core data flow

```
EventAdapter.fetch_events()
  → ProfileBuilder.build(policy_engine?)  # builds BehaviorProfile per subject, seeded by policy
  → RareDestinationDetector.detect()      # compares event to existing profile
  → PeerDeviationDetector.detect()        # compares event to current-batch peer profiles
  → FindingStore.add()
  → NarrativeBuilder.build()              # rolls findings into per-subject Narrative
  → GNATConnector.to_record()             # converts Finding/Narrative → GNAT record dict
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

## What's implemented

- Two adapters: `SampleEventAdapter` (fixture) and `CsvEventAdapter` (named-column CSV, ISO/epoch timestamps)
- Two detectors: `RareDestinationDetector` and `PeerDeviationDetector`
- `PolicyEngine` — loads per-subject/group rules from YAML; seeds profiles before telemetry arrives
- `NarrativeBuilder` — rolls per-subject findings into a `Narrative` with severity rollup and type frequency
- YAML config loader — `load_settings(path)` in `sensegnat/config/settings.py`
- Disk persistence — `JsonProfileStore` and `JsonFindingStore` in `sensegnat/storage/json_store.py`
- `sensegnat.common` — `to_dict` (recursive JSON-safe serializer) and `utcnow` (timezone-aware now)
- CI — `.github/workflows/ci.yml` runs `pip install -e . && pytest` on push/PR to main
- 51 passing unit tests

## Not yet implemented

- Time-window drift detector — referenced in ADRs; no code yet
- Policy rule-violation detector — referenced in ADRs; no code yet
- Real network adapters — Zeek, Suricata, or live GNAT telemetry feeds
- Disk store merging — `JsonProfileStore` replaces profiles on `put_many`; no incremental merge yet

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
