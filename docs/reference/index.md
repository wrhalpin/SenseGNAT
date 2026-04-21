# Reference Index

Reference documentation for SenseGNAT. These documents describe the system precisely. They are consulted, not read cover-to-cover.

---

## Documents

| Document | Description |
|---|---|
| [Data Model](data-model.md) | All core frozen dataclasses: `NormalizedNetworkEvent`, `BehaviorProfile`, `Finding`, `Narrative`, and the canonical subject identity rule. |
| [Detectors](detectors.md) | All four anomaly detectors (`RareDestinationDetector`, `PeerDeviationDetector`, `PolicyViolationDetector`, `TimeWindowDriftDetector`): signatures, logic, finding properties, and evidence keys. |
| [Adapters](adapters.md) | The `EventAdapter` ABC and all four concrete implementations (`SampleEventAdapter`, `CsvEventAdapter`, `ZeekConnLogAdapter`, `SuricataEveAdapter`): constructor parameters, column/field mappings, and parse rules. |
| [Policy Schema](policy-schema.md) | The YAML policy file format: `groups` and `subjects` structure, field types, resolution rules (subject rules union with group rules), and a complete annotated example. |
| [Configuration](configuration.md) | `SenseGNATSettings` and its sub-models (`RuntimeSettings`, `StorageSettings`, `GNATSettings`), `load_settings(path)`, all fields with types and defaults, and a complete annotated YAML example. |
| [GNAT Connector](gnat-connector.md) | `GNATConnector` constructor, all methods, the TAXII 2.1 transport details, `PushResult`, and complete STIX Indicator and Note field schemas with example JSON. |

---

## Quick lookup

| I want to know... | Go to |
|---|---|
| What fields does `NormalizedNetworkEvent` have? | [Data Model — NormalizedNetworkEvent](data-model.md#normalizednetworkevent) |
| How is `subject_id` derived? | [Data Model — Subject Identity](data-model.md#subject-identity) |
| What does `BehaviorProfile.merge()` do? | [Data Model — BehaviorProfile](data-model.md#behaviourprofile) |
| What evidence keys does each detector produce? | [Detectors](detectors.md) |
| What score/severity does each detector emit? | [Detectors — Comparison Table](detectors.md#comparison-table) |
| What CSV columns are required? | [Adapters — CsvEventAdapter](adapters.md#csveventadapter) |
| How does Zeek column mapping work? | [Adapters — ZeekConnLogAdapter](adapters.md#zeekconnlogadapter) |
| Which Suricata event types are processed? | [Adapters — SuricataEveAdapter](adapters.md#suricataevadapter) |
| How do group and subject policy rules combine? | [Policy Schema — Resolution rules](policy-schema.md#resolution-rules) |
| What YAML keys does the policy file accept? | [Policy Schema](policy-schema.md) |
| What are the default config values? | [Configuration](configuration.md) |
| What STIX fields does a Finding produce? | [GNAT Connector — STIX Indicator fields](gnat-connector.md#stix-indicator-fields-for-findings) |
| What does `PushResult.ok` mean? | [GNAT Connector — PushResult](gnat-connector.md#pushresult) |
