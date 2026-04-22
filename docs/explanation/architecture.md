# Architecture: How SenseGNAT Is Structured and Why

## What SenseGNAT Is and Where It Fits

GNAT is a threat intelligence platform. It manages STIX/TAXII feeds, hosts investigations, generates reports, and orchestrates analyst workflows. What GNAT does not do natively is watch *behavior over time*. It ingests intelligence about known threats but does not build per-entity baselines from raw network telemetry or detect drift from those baselines.

SenseGNAT fills that gap. It is a standalone behavioral analytics capability that sits beside GNAT rather than inside it. SenseGNAT watches who is talking to whom, builds a behavioral baseline for each network subject, runs explainable detectors against those baselines, and emits findings back into GNAT as STIX 2.1 objects. From GNAT's perspective, SenseGNAT looks like a specialized sensor: it produces `indicator` and `note` objects that flow through the standard TAXII 2.1 collection endpoint and become first-class objects inside GNAT investigations and reports.

This separation is intentional. ADR-001 explains the reasoning in detail, but the short version is that behavioral analytics has its own storage, scheduling, and lifecycle requirements that do not belong in GNAT core. Keeping SenseGNAT standalone means GNAT deployments that do not need behavioral analytics carry no overhead from it, and SenseGNAT can evolve its baseline model, detector set, and storage strategies independently.

---

## The Three-Layer Design

SenseGNAT's internal structure follows three layers, each with a clear responsibility boundary.

### Ingestion Layer

The ingestion layer is responsible for turning raw network telemetry — whatever the source format — into a uniform internal representation. Every source adapter subclasses `EventAdapter` (defined in `sensegnat/ingestion/base.py`) and implements a single method:

```python
def fetch_events(self) -> Iterable[NormalizedNetworkEvent]:
    ...
```

The resulting `NormalizedNetworkEvent` objects are the only currency the rest of the system accepts. Nothing downstream knows or cares whether the events came from a Zeek conn.log, a Suricata EVE JSON file, a CSV export, or a synthetic fixture. This is the normalization contract.

Five adapters ship with SenseGNAT:

- `SampleEventAdapter` — a fixture adapter that generates synthetic events for testing and examples
- `CsvEventAdapter` — parses named-column CSV files with ISO 8601 or Unix-epoch timestamps
- `ZeekConnLogAdapter` — parses Zeek `conn.log` TSV files using the dynamic `#fields` header
- `SuricataEveAdapter` — parses Suricata EVE JSON `flow` and `alert` records
- `GNATTelemetryAdapter` — consumes live sensor records from the Kafka topic shared with GNAT (`gnat.telemetry`), handling `netflow`, `ids_alert`, and `honeypot` sensor types with full NetFlow v9 field name support

Writing a new adapter means subclassing `EventAdapter`, implementing `fetch_events()`, and wiring it into `SenseGNATService`. The core pipeline requires no changes.

### Analytics Layer

The analytics layer is where behavior is modeled and anomalies are detected. It has two components: `ProfileBuilder` and the detector set.

`ProfileBuilder` (in `sensegnat/behavior/profiler.py`) consumes a list of `NormalizedNetworkEvent` objects and produces a `dict[str, BehaviorProfile]` mapping each subject ID to its behavioral baseline for that batch. A `BehaviorProfile` is a frozen dataclass holding three frozensets: the destinations, ports, and protocols that subject has been observed using. It is deliberately minimal — a record of observed behavior, not a statistical model.

The four detectors each examine individual events against these profiles:

- `RareDestinationDetector` — fires when a subject contacts a destination not in their profile
- `PeerDeviationDetector` — fires when a subject's destination or port is not present in any peer profile
- `PolicyViolationDetector` — fires when an event's destination or port falls outside the YAML allow-list for that subject
- `TimeWindowDriftDetector` — fires when the current event batch introduces a high proportion of novel destinations relative to the established profile size

Each detector is a pure function of its inputs. No detector holds mutable state between invocations. Each returns either a `Finding` or `None`.

### Output Layer

The output layer converts the internal `Finding` and `Narrative` objects into STIX 2.1 and delivers them to GNAT. `GNATConnector` (in `sensegnat/connectors/gnat_connector.py`) handles both serialization and transport.

`to_record()` and `finding_to_stix()` convert a `Finding` to a STIX `indicator` dict. `narrative_to_record()` and `narrative_to_stix()` convert a `Narrative` to a STIX `note` dict. When `base_url` and `api_key` are configured, `push_findings()` and `push_narratives()` POST these objects as a STIX bundle to the GNAT TAXII 2.1 collection endpoint. When no credentials are configured, the connector operates in record-only mode: it serializes to STIX dicts and returns them without making any network calls. This mode is used by the examples and most tests.

---

## Data Flow

The full pipeline through `SenseGNATService.run_once()`:

```
EventAdapter.fetch_events()
  │
  │  Returns Iterable[NormalizedNetworkEvent]
  ▼
ProfileBuilder.build(events, policy_engine?)
  │
  │  Builds BehaviorProfile per subject_id
  │  Policy seeds the profile before telemetry is applied
  │  pre_run_profiles = snapshot from ProfileStore (used by detectors)
  ▼
For each event:
  RareDestinationDetector.detect(event, pre_run_profile)
  PeerDeviationDetector.detect(event, pre_run_profile, peer_profiles)
  PolicyViolationDetector.detect(event, policy_engine)
  TimeWindowDriftDetector.detect(subject_id, subject_events, pre_run_profile)
  │
  │  Each returns Finding | None
  ▼
FindingStore.add(finding)   ← persists findings
  │
  ▼
NarrativeBuilder.build(subject_id, findings)
  │
  │  Rolls all findings per subject into one Narrative
  │  severity = highest across findings
  │  score    = peak across findings
  ▼
GNATConnector.push_findings(findings)   → STIX Indicator → GNAT TAXII endpoint
GNATConnector.push_narratives(narratives) → STIX Note → GNAT TAXII endpoint
  │
  ▼
ProfileStore.put_many(new_profiles)
  │
  │  Merges via BehaviorProfile.merge() — baselines grow across runs
  ▼
run_once() returns list[dict]  (STIX records produced this run)
```

One critical sequencing detail: the detectors receive the *pre-run snapshot* of each profile, not the profile being built during the current run. This means the same event cannot simultaneously build a profile entry and match that entry — so the very first event a subject generates never fires a rare-destination finding. This is intentional; see the "Profile Accumulation" section below.

---

## Subject Identity

Throughout the system, a subject is identified by a single canonical string:

```python
subject_id = event.source_user or event.source_host
```

If the adapter provides a `source_user`, that is the subject. If not, the `source_host` is used. This rule is applied identically by `ProfileBuilder`, every detector, `NarrativeBuilder`, and the stores. There is no secondary or composite key.

The reason for user-over-host precedence is that user identity travels across hosts. If `alice` logs into `laptop-01` on Monday and `laptop-02` on Tuesday, her profile should accumulate across both machines. If only the host is available (as is the case for raw Zeek or Suricata data that carries no user context), the host itself is the subject.

ADR-004 covers the entity-centric design choice in more depth.

---

## Policy and Baseline Seeding

Before any telemetry is processed, `ProfileBuilder` consults the `PolicyEngine` to pre-populate each subject's profile with their policy-allowed destinations, ports, and protocols. This is called seeding.

The `PolicyEngine` (in `sensegnat/policy/engine.py`) loads YAML rules that define per-subject and per-group allow-lists. A rule might read: "members of the `engineering` group are allowed to contact `203.0.113.10`, `10.0.0.1`, and `10.0.0.2`." When `ProfileBuilder` processes events for a subject in that group, it first loads those allowed destinations into the profile's `common_destinations` frozenset. Then it adds the destinations observed in the current event batch on top.

The result is that on the first day of data collection, a subject contacting a policy-allowed destination does not generate a `rare-destination` finding. Without seeding, every destination would look rare on day one regardless of whether it was expected. This is the cold-start problem — policy seeding is how SenseGNAT addresses it.

The `PolicyViolationDetector` completes the picture from the other direction: it fires when an event's destination or port is *outside* the allow-list. Together, seeding and `PolicyViolationDetector` mean the system can distinguish three states for any observed destination:

1. In policy and in the observed baseline — expected, no finding
2. Not in policy but in the observed baseline — was happening and allowed; watch for drift
3. In the event but not in policy — violation; finding fires

---

## Profile Accumulation

`BehaviorProfile` objects are immutable frozen dataclasses. When a run completes, the `ProfileStore.put_many()` call does not overwrite existing profiles. Instead, it merges them:

```python
def merge(self, incoming: BehaviorProfile) -> BehaviorProfile:
    return BehaviorProfile(
        profile_id=self.profile_id,
        subject_id=self.subject_id,
        peer_group=incoming.peer_group,
        common_destinations=self.common_destinations | incoming.common_destinations,
        common_ports=self.common_ports | incoming.common_ports,
        common_protocols=self.common_protocols | incoming.common_protocols,
    )
```

Each field is a union. A destination that appeared in any past run stays in the profile permanently. Peer group from the incoming profile takes precedence — this lets policy updates propagate.

The practical consequence is that baselines improve over time. A subject who legitimately contacts ten different destinations over the course of a month builds a profile that includes all ten. On month two, none of those destinations generate findings. Novel destinations in month two still do. The longer SenseGNAT runs without a profile reset, the richer and more accurate the baselines become, and the lower the false-positive rate.

The disk-backed `JsonProfileStore` calls `merge()` inside `put_many()`, so accumulation persists across process restarts. The in-memory `InMemoryProfileStore` does the same within a single process session.

---

## Why STIX 2.1

GNAT's native wire format is STIX 2.1 over TAXII 2.1. Using STIX for SenseGNAT output means findings and narratives arrive in GNAT as first-class objects without any translation layer. They appear in investigation timelines, can be referenced by reports, and can flow outward to other TAXII consumers.

SenseGNAT findings map to STIX `indicator` objects. The standard STIX fields (`pattern`, `valid_from`, `confidence`, `indicator_types`) carry the detection signal in terms any STIX consumer understands. SenseGNAT-specific metadata lives in custom extension properties following two naming conventions:

- `x_gnat_*` — properties that align with GNAT's standard telemetry schema. These use the same property names as other GNAT sensors (`x_gnat_sensor_id`, `x_gnat_sensor_type`, `x_gnat_signature`, `x_gnat_tags`, `x_gnat_tlp`). GNAT indexing and filtering logic that works on other sensor types works on SenseGNAT output without modification.

- `x_sensegnat_*` — properties specific to the behavioral analytics domain (`x_sensegnat_score`, `x_sensegnat_severity`, `x_sensegnat_summary`, `x_sensegnat_evidence`, `x_sensegnat_subject_id`). These carry the explainability data — the score, the human-readable summary, and the evidence dict.

SenseGNAT narratives map to STIX `note` objects. Notes are a natural fit for per-subject summaries: they have a `content` field (the narrative summary sentence) and `object_refs` that can point to the associated indicators once full GNAT integration is complete.

ADR-005 documents the decision to maintain custom behavior objects alongside STIX-compatible output.

---

## The Bidirectional GNAT Loop

SenseGNAT operates as a bidirectional partner to GNAT. The output layer (`GNATConnector`) produces STIX 2.1 bundles and POSTs them to the GNAT TAXII 2.1 collection endpoint — findings flow *into* GNAT as first-class `indicator` and `note` objects.

`GNATTelemetryAdapter` closes the other half of the loop. It taps the same raw Kafka topic that GNAT's `KafkaSourceReader` consumes (`gnat.telemetry`), giving SenseGNAT access to the full network five-tuple before GNAT converts records to STIX Indicators. This design choice was deliberate: reading from GNAT's TAXII endpoint would only yield processed `indicator` objects — single IPs with no port, bytes, or peer context — and that is not enough data to build behavioral profiles. The Kafka stream carries the full `SensorEvent` payload that profiling requires.

The result is a complete closed loop: GNAT sensors publish telemetry to Kafka → `GNATTelemetryAdapter` reads it and normalizes it → SenseGNAT builds profiles and detects anomalies → `GNATConnector` pushes behavioral findings back into GNAT investigations. Each system does what it does best: GNAT manages intelligence and workflows; SenseGNAT manages behavioral baselines and anomaly detection.
