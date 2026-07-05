# Changelog

All notable changes to SenseGNAT are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-04

### Added

- `sensegnat` CLI entry point — `sensegnat run --config <yaml>` runs the
  pipeline once; `--interval N` re-runs on a loop; `-v/-vv` controls log
  level; `--version` prints the package version.
- `adapter:` config section and `build_adapter()` factory
  (`sensegnat/ingestion/factory.py`) — adapters are now constructible
  from YAML config instead of code only.
- Environment-variable interpolation in config — `${VAR}` references in
  YAML string values are expanded from the environment at load time, so
  secrets like `api_key: "${GNAT_API_KEY}"` stay out of config files.
- `SplunkEventAdapter` — SPL query-driven ingestion via the Splunk REST
  API with CIM field mapping, vendor fallbacks, token or basic auth, and
  pagination (`pip install sensegnat[splunk]`).
- `GNATTelemetryAdapter` — live sensor telemetry from GNAT's Kafka topic
  with NetFlow v9 field aliases (`pip install sensegnat[kafka]`).
- Cross-tool investigation context — findings and narratives stamp
  `x_gnat_investigation_id` via policy rules, Kafka telemetry hints, or a
  feature-flagged GNAT subject-lookup API; tagged objects are wrapped in
  one STIX Grouping per investigation per run.
- `GNATConnector.push_objects()` — pushes pre-serialized STIX objects so
  Grouping `object_refs` stay valid.
- Release workflow — tagged `v*` pushes build sdist/wheel and attach them
  to a GitHub Release.

### Changed

- `SenseGNATService.run_once()` now pushes the serialized STIX bundle to
  GNAT when the connector is configured (record-only mode still skips).
- mypy CI check is now blocking; `[tool.mypy]` configuration added.

### Fixed

- `JsonFindingStore` no longer drops `investigation_id` /
  `investigation_link_type` when reloading persisted findings from disk.

## [0.1.0] - 2026-05-01

### Added

- Initial release: `EventAdapter` contract with sample, CSV, Zeek
  conn.log, and Suricata EVE adapters; four explainable detectors (rare
  destination, peer deviation, policy violation, time-window drift);
  policy-guided baselining via YAML `PolicyEngine`; per-subject
  `NarrativeBuilder`; `GNATConnector` with STIX 2.1 Indicator/Note
  serialization and TAXII 2.1 bundle POST; in-memory and JSON-backed
  profile/finding stores with merge-on-write accumulation; Pydantic
  settings with YAML loader; Diátaxis documentation and GitHub Pages
  site.

[Unreleased]: https://github.com/wrhalpin/SenseGNAT/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/wrhalpin/SenseGNAT/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wrhalpin/SenseGNAT/releases/tag/v0.1.0
