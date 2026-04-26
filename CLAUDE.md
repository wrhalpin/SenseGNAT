# SenseGNAT — Claude Code Guide

## What this project is

SenseGNAT is a standalone behavior analytics capability that integrates into GNAT via a connector contract. It builds per-entity behavioral baselines from normalized network telemetry, runs explainable detectors against those baselines, and emits structured findings back into GNAT as STIX 2.1 objects over TAXII 2.1.

Tagline: "Behavior is the signal."

See `docs/archtiecture/adrs/` for the five decisions that shaped the design. For user-facing documentation, see `docs/` (tutorials, how-to guides, reference, explanation).

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
  detection/    # Explainable detectors (RareDestinationDetector, PeerDeviationDetector, etc.)
  storage/      # InMemoryProfileStore / InMemoryFindingStore + JSON-backed equivalents
  connectors/   # GNATConnector — STIX 2.1 serialization + TAXII 2.1 transport
  config/       # Pydantic settings models + load_settings(path) YAML loader
  policy/       # PolicyEngine — loads per-subject/group rules from YAML
  narrative/    # NarrativeBuilder — rolls per-subject findings into a Narrative
  api/          # SenseGNATService — the main orchestrator
  common/       # Shared utilities: to_dict (serialization), utcnow (time)

tests/          # pytest suite (project root, not inside the package)
examples/       # Runnable scripts, config templates, and sample data
docs/           # Diátaxis docs: tutorials/, how-to/, reference/, explanation/, ADRs
```

---

## Core data flow

```
EventAdapter.fetch_events()
  → ProfileBuilder.build(policy_engine?)  # builds BehaviorProfile per subject, seeded by policy
  → RareDestinationDetector.detect()      # compares event to existing profile
  → PeerDeviationDetector.detect()        # compares event to current-batch peer profiles
  → PolicyViolationDetector.detect()      # checks event against YAML allow-lists
  → TimeWindowDriftDetector.detect()      # detects burst of novel destinations this window
  → FindingStore.add()
  → NarrativeBuilder.build()              # rolls findings into per-subject Narrative
  → GNATConnector.push_findings()         # STIX Indicator → GNAT TAXII endpoint
  → GNATConnector.push_narratives()       # STIX Note → GNAT TAXII endpoint
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

- Six adapters: `SampleEventAdapter` (fixture), `CsvEventAdapter` (named-column CSV, ISO/epoch timestamps), `ZeekConnLogAdapter` (Zeek conn.log TSV, dynamic #fields header), `SuricataEveAdapter` (EVE JSON flow/alert records), `GNATTelemetryAdapter` (live Kafka topic, optional `kafka-python-ng`), `SplunkEventAdapter` (SPL query via Splunk REST API, CIM field mapping, optional `splunk-sdk`)
- Four detectors: `RareDestinationDetector`, `PeerDeviationDetector`, `PolicyViolationDetector`, `TimeWindowDriftDetector`
- `PolicyEngine` — loads per-subject/group rules from YAML; seeds profiles before telemetry arrives
- `NarrativeBuilder` — rolls per-subject findings into a `Narrative` with severity rollup and type frequency
- `GNATConnector` — fully implemented: `finding_to_stix()` → STIX 2.1 Indicator, `narrative_to_stix()` → STIX 2.1 Note, `push_findings()` / `push_narratives()` → TAXII 2.1 bundle POST; `to_record()` and `narrative_to_record()` remain as record-only aliases
- `PushResult` dataclass — `pushed: int`, `errors: list[str]`, `ok: bool` property
- `GNATSettings` sub-model added to `SenseGNATSettings` (`base_url`, `api_key`, `workspace`, `tlp`, `confidence`, `timeout`)
- YAML config loader — `load_settings(path)` in `sensegnat/config/settings.py`
- Disk persistence — `JsonProfileStore` and `JsonFindingStore` in `sensegnat/storage/json_store.py`
- Profile accumulation — `BehaviorProfile.merge()` unions observation sets across runs; stores call it on `put_many`
- `sensegnat.common` — `to_dict` (recursive JSON-safe serializer) and `utcnow` (timezone-aware now)
- CI — `.github/workflows/ci.yml` runs `pip install -e . && pytest` on push/PR to main
- `GNATTelemetryAdapter` — reads live sensor records from the Kafka topic shared with GNAT; handles `netflow`, `ids_alert`, `honeypot` sensor types; supports NetFlow v9 field names; optional `kafka-python-ng` dependency (`pip install kafka-python-ng`)
- `SplunkEventAdapter` — runs a caller-supplied SPL query against Splunk's REST API; maps CIM fields (`src`, `dest`, `transport`, `bytes_out/in`) with vendor fallbacks; token or u/p auth; paginated; optional `splunk-sdk` dependency (`pip install sensegnat[splunk]`)
- 322 passing tests (unit + integration)
- Diátaxis documentation structure — `docs/tutorials/`, `docs/how-to/`, `docs/reference/`, `docs/explanation/`
- GitHub Pages site — `docs/_config.yml`, `docs/index.md`, brand palette CSS override, full logo kit in `docs/assets/images/`

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
