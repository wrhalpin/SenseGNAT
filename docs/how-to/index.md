# How-to guides

These guides are goal-oriented. They assume you already understand SenseGNAT
basics and want to accomplish a specific task.

---

## Guides

### [Add a behavioral detector](add-a-detector.md)

Write a new stateless detector class, place it in `sensegnat/detection/`, wire
it into `SenseGNATService`, and cover it with pytest tests — including a
complete worked example: `HighByteVolumeDetector`.

### [Configure policies](configure-policies.md)

Write a YAML policy file to seed behavioral baselines with known-good
destinations, ports, and protocols before telemetry arrives, so legitimate
traffic never fires as "rare"; covers group inheritance, subject-level
exceptions, and common allow-listing patterns.

### [Integrate with GNAT](integrate-with-gnat.md)

Push findings and narratives into a running GNAT instance as STIX 2.1
Indicators and Notes over TAXII 2.1; covers connector configuration, loading
credentials from YAML, a full example STIX payload, error handling, and
record-only mode for local development.

### [Use persistent storage](use-persistent-storage.md)

Switch from the default in-memory stores to `JsonProfileStore` and
`JsonFindingStore` so behavioral profiles and findings survive process
restarts; covers configuration paths, the JSON file format on disk, how profile
merge accumulates baselines across runs, and when to prefer each store type.

---

## Related reference

- `sensegnat/detection/` — existing detector implementations
- `sensegnat/api/service.py` — `SenseGNATService.run_once()` wiring
- `sensegnat/config/settings.py` — `SenseGNATSettings` and `load_settings()`
- `examples/sensegnat.example.yaml` — annotated settings template
- `examples/sensegnat.example.policies.yaml` — annotated policy template
- `docs/archtiecture/adrs/` — the five architecture decision records
