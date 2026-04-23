---
layout: default
title: SenseGNAT
description: Behavior analytics companion to GNAT. Network profiling and behavior analysis — see more, know more, stop more.
---

<p class="kicker">GNAT-o-sphere / behavior analytics</p>

<div style="display: flex; align-items: center; gap: 2.5rem; margin-bottom: 2rem;">
  <div style="flex: 1; min-width: 0;">
    <p class="kicker">GNAT-o-sphere / core platform</p>
    <h1 style="margin-top: 0;">SenseGNAT</h1>
    <p>Behavior analytics companion to GNAT. Builds per-entity baselines from
    normalized network telemetry, runs explainable detectors against those
    baselines, and emits STIX 2.1 findings back into GNAT via TAXII 2.1.</p>
    <p><strong>Behavior is the signal.</strong></p>
    <p>Source: <a href="https://github.com/wrhalpin/SenseGNAT"><code>github.com/wrhalpin/SenseGNAT</code></a>.</p>
  </div>
  <div style="flex-shrink: 0;">
    <img src="assets/images/sensegnat-logo-512.png"
         alt="SenseGNAT mascot — a GNAT in a deep-violet suit, fingers at its temples, signal arcs radiating from a shield badge"
         width="300">
  </div>
</div>

---

## Documentation

Organised with the [Diátaxis](https://diataxis.fr/) framework. Four
quadrants for four kinds of reader-intent:

|                | **Action (doing)**                  | **Study (reading)**              |
|----------------|-------------------------------------|----------------------------------|
| **Learning**   | [Tutorials](tutorials/)             | [Explanation](explanation/)      |
| **Working**    | [How-to guides](how-to/)            | [Reference](reference/)          |

### Start here if you're…

- **New to SenseGNAT** → [tutorials/01 — Getting started](tutorials/01-getting-started.md)
- **Writing a custom adapter** → [tutorials/02 — Write a custom adapter](tutorials/02-write-a-custom-adapter.md)
- **Adding a new detector** → [how-to/add-a-detector](how-to/add-a-detector.md)
- **Pushing findings into GNAT** → [how-to/integrate-with-gnat](how-to/integrate-with-gnat.md)
- **Understanding the architecture** → [explanation/architecture](explanation/architecture.md)
- **Looking up a data type** → [reference/data-model](reference/data-model.md)

---

## What SenseGNAT does, end to end

1. **Ingest** — an `EventAdapter` reads telemetry from any source (Zeek
   conn.log, Suricata EVE JSON, CSV, GNAT's live Kafka telemetry topic, or
   custom) and yields `NormalizedNetworkEvent` objects with a consistent
   five-tuple schema.

2. **Profile** — `ProfileBuilder` aggregates events into per-entity
   `BehaviorProfile` objects. Profiles are seeded from YAML policy rules
   before telemetry arrives, so day-one traffic to approved destinations
   is never flagged as anomalous.

3. **Detect** — four stateless, explainable detectors run against each
   event and its profile:
   - `RareDestinationDetector` — flags destinations absent from the
     entity's baseline.
   - `PeerDeviationDetector` — flags destinations unique to one entity
     within its peer group.
   - `PolicyViolationDetector` — flags traffic that violates an explicit
     allow-list rule.
   - `TimeWindowDriftDetector` — flags a burst of new destinations in
     the current batch relative to the established baseline size.

4. **Narrate** — `NarrativeBuilder` rolls per-entity findings into a
   `Narrative` with severity rollup, type frequency, and a human-readable
   summary.

5. **Publish** — `GNATConnector` converts findings to STIX 2.1 Indicator
   objects and narratives to STIX 2.1 Note objects, then POSTs them as
   STIX bundles to the GNAT TAXII 2.1 collection endpoint.

---

## Key design choices

- **Explainability first.** Every `Finding` carries a `summary`
  (human-readable sentence) and an `evidence` dict (the specific data
  that triggered it). Analysts know exactly what to look at.
  Rationale: [explanation/explainability-first](explanation/explainability-first.md).

- **Policy-guided baselining.** Policy seeds the baseline with known-good
  patterns before telemetry arrives, solving the cold-start problem.
  Telemetry then refines the baseline over time.
  Rationale: [explanation/policy-guided-baselining](explanation/policy-guided-baselining.md).

- **Profile accumulation across runs.** `BehaviorProfile.merge()` unions
  observation sets on every write, so baselines grow without losing history.

- **STIX 2.1 as the output contract.** Findings surface in GNAT as
  standard Indicator and Note objects with `x_gnat_*` telemetry properties
  and `x_sensegnat_*` behavioral metadata.
  See: [reference/gnat-connector](reference/gnat-connector.md).

- **Standalone by design.** SenseGNAT integrates with GNAT via connector
  contract — it does not modify GNAT core. Independent release cadence,
  independent storage, independent scheduling.

---

## What's implemented

| Area | Component |
|---|---|
| **Adapters** | `SampleEventAdapter`, `CsvEventAdapter`, `ZeekConnLogAdapter`, `SuricataEveAdapter`, `GNATTelemetryAdapter` |
| **Detectors** | `RareDestinationDetector`, `PeerDeviationDetector`, `PolicyViolationDetector`, `TimeWindowDriftDetector` |
| **Storage** | `InMemoryProfileStore`, `InMemoryFindingStore`, `JsonProfileStore`, `JsonFindingStore` |
| **Policy** | `PolicyEngine` — YAML-driven group/subject allow-lists with peer-group assignment |
| **Narrative** | `NarrativeBuilder` — per-entity severity rollup and type-frequency summary |
| **Connector** | `GNATConnector` — STIX 2.1 Indicator + Note, TAXII 2.1 POST with Bearer auth |
| **Config** | `SenseGNATSettings` — Pydantic model, YAML loader |
| **Tests** | 231 passing tests |

---

## Status

All three phases are complete. Five source adapters, four explainable
detectors, a fully-wired GNAT connector, and a live Kafka telemetry adapter
are shipped. Profile accumulation, policy-guided baselining, and narrative
building are complete. SenseGNAT now operates as a bidirectional partner
to GNAT: consuming raw sensor telemetry from GNAT's Kafka topic and publishing
behavioral findings back into GNAT via TAXII 2.1.

---

## The GNAT-o-sphere

SenseGNAT is one of three add-ons that plug into GNAT, the core threat-intel platform. Every sibling emits STIX 2.1 objects and is pulled by GNAT through a documented connector rather than writing into its database directly.
<p>
<a class=“flow-doc-link” href=“workflow.html”>Canonical workflow documentation →</a>
</p>
<div class="gnatophere-grid">

  <div class="gnat-card gnat-card-gnat">
    <span class="gnat-card-tag">Core Platform</span>
    <h3>GNAT</h3>
    <p>The hub platform for threat intelligence. Connector abstraction, STIX 2.1 modeling, reports, investigations, and workflow automation.</p>
    <a class="gnat-card-link gnat-link-gnat" href="https://wrhalpin.github.io/GNAT/">Learn more</a>
  </div>

  <div class="gnat-card gnat-card-sand">
    <span class="gnat-card-tag">Addon</span>
    <h3>SandGNAT</h3>
    <p>Automated malware sandbox analysis — detonate binaries in isolated VMs, capture behavioral artifacts, emit STIX 2.1 objects.</p>
    <a class="gnat-card-link gnat-link-sand" href="https://wrhalpin.github.io/SandGNAT/">Learn more</a>
  </div>

  <div class="gnat-card gnat-card-red">
    <span class="gnat-card-tag">Addon</span>
    <h3>RedGNAT</h3>
    <p>Continuous automated red teaming — ingest threat intel, construct adversary emulation scenarios, execute with safety controls.</p>
    <a class="gnat-card-link gnat-link-red" href="https://wrhalpin.github.io/RedGNAT/">Learn more</a>
  </div>

</div>

Licensed under [Apache 2.0](https://github.com/wrhalpin/SenseGNAT/blob/main/LICENSE).
