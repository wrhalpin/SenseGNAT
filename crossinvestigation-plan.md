# SenseGNAT — Cross-Tool Investigation Context Plan

**Scope:** SenseGNAT’s side of the GNAT-o-sphere investigation-context work. The shared contract lives in the GNAT repo at `docs/reference/investigation-context-schema.md`. **Read that first.**

**Intended audience:** Claude Code working in the `wrhalpin/SenseGNAT` repo.

-----

## Context that must not be re-derived

SenseGNAT’s actual layout (not what the original plan assumed):

- `sensegnat/` — the package.
  - `behavior/profiler.py` — `ProfileBuilder`, `BehaviorProfile`.
  - `policy/engine.py` — `PolicyEngine`, YAML rule loading.
  - `narrative/` — `NarrativeBuilder` and the `Narrative` type.
  - `connectors/gnat_connector.py` — `GNATConnector`: STIX 2.1 serialization + TAXII 2.1 transport to GNAT.
  - `storage/json_store.py` — `JsonProfileStore` (merge-on-write profile persistence).
  - `api/service.py` — `SenseGNATService.run_once()` orchestrates the full pipeline.
- Source adapters in `sensegnat/adapters/` (or similar — confirm in-repo): `SampleEventAdapter`, `CsvEventAdapter`, `ZeekConnLogAdapter`, `SuricataEveAdapter`, `GNATTelemetryAdapter` (reads live sensor telemetry from GNAT’s Kafka topic `gnat.telemetry`).
- Four detectors: `RareDestinationDetector`, `PeerDeviationDetector`, `PolicyViolationDetector`, `TimeWindowDriftDetector`.
- Emits STIX 2.1 `indicator` (findings) and `note` (narratives) via TAXII 2.1 into GNAT.
- 231 passing tests.

**Key operational reality:** SenseGNAT is a continuous service. Detectors fire against live telemetry, not on a per-investigation basis. This shapes the integration design. The original plan’s “supply investigation_id by config, rule, tag, or enrichment” was too vague; the concrete options are laid out below.

If any of the above has changed since this plan was written, confirm the current state in-conversation before proceeding.

-----

## Goal

Let SenseGNAT findings land in the right GNAT investigation’s evidence graph, without forcing SenseGNAT into a per-investigation execution model.

-----

## The shared contract (quick reference)

Three custom STIX properties, stamped on every emitted `indicator` and `note`:

- `x_gnat_investigation_id`
- `x_gnat_investigation_origin = "sensegnat"`
- `x_gnat_investigation_link_type` — almost always `"inferred"` for SenseGNAT output, since detections are behavioural. Policy violations can be `"confirmed"` when the policy rule was authored as part of an investigation.

Every `run_once()` invocation that produces findings must also emit a wrapping STIX `Grouping` carrying the same three properties.

-----

## Phase 0 — Decide how investigation_id gets attached

SenseGNAT needs three distinct attachment paths, because no single one covers the operational reality:

|Path                  |When it fires                                                                                                     |Link type  |Notes                                                                         |
|----------------------|------------------------------------------------------------------------------------------------------------------|-----------|------------------------------------------------------------------------------|
|**A. Policy-declared**|Finding comes from a policy rule that declares an investigation_id.                                               |`confirmed`|An analyst authored the rule specifically for this investigation.             |
|**B. Subject lookup** |Detector fires against a subject (IP/host/user) that’s already a node in an active investigation’s evidence graph.|`inferred` |SenseGNAT queries GNAT at emission time.                                      |
|**C. Unattached**     |Finding has no known investigation; emitted without the properties.                                               |(none)     |Default for general-purpose monitoring. GNAT’s correlator may attach it later.|

Path B requires a runtime GNAT lookup, which adds a dependency on GNAT reachability. It must degrade gracefully: on GNAT timeout or error, fall back to path C. Never block detector emission on a GNAT call.

-----

## Phase 1 — Policy rule extension (Path A)

### 1.1 Rule schema

Policy rules are YAML today. Extend the schema:

```yaml
rules:
  - name: finance-servers-egress-policy
    subjects: ["host:finance-*"]
    allow_destinations: ["1.2.3.0/24"]
    allow_ports: [443]
    investigation_id: "IC-2026-0001"       # new
    investigation_link_type: "confirmed"    # new, defaults to "confirmed"
```

Both are optional. When present, any finding produced by this rule carries the declared context.

### 1.2 Policy engine changes

In `sensegnat/policy/engine.py`:

- Parse and validate the two new fields.
- Surface them on the loaded rule object.

### 1.3 Detector awareness

`PolicyViolationDetector` is the obvious consumer. Update it to thread the rule’s investigation context into the finding it emits.

The other three detectors (`RareDestinationDetector`, `PeerDeviationDetector`, `TimeWindowDriftDetector`) don’t operate against policy rules directly — they use profiles. They’ll use path B.

-----

## Phase 2 — Subject lookup (Path B)

### 2.1 GNATConnector addition

In `sensegnat/connectors/gnat_connector.py`, add:

```python
def find_investigations_for_subject(
    self,
    subject_ref: str,
    timeout_seconds: float = 2.0,
) -> list[str]:
    """Call GNAT's investigation search. Returns investigation IDs whose
    EvidenceGraph contains this subject. Empty list on timeout or error."""
```

This hits the new GNAT endpoint `GET /api/investigations?subject=<ref>` (GNAT plan Phase 1.2 `find_by_subject`). It must:

- Use a short timeout (2s default).
- Swallow all exceptions and return `[]` on failure.
- Cache positive results for a short window (e.g., 60s) keyed by subject to avoid hammering GNAT during a detection burst.

### 2.2 Finding enrichment step

In `sensegnat/api/service.py`’s `run_once()`:

- After detectors produce findings, but before `GNATConnector.send()`, run a new enrichment pass: for each finding whose subject is a known node-shape (host, IP, user), call `find_investigations_for_subject`.
- If one match: stamp `x_gnat_investigation_id` with that ID, link type `"inferred"`.
- If multiple matches: stamp with the single most recently updated investigation ID. Add a STIX `note` listing the others as candidates. Link type `"suggested"` on the alternatives.
- If zero matches: leave the finding unstamped.

This enrichment pass is **feature-flagged off by default** — behaviour flag `SENSEGNAT_INVESTIGATION_LOOKUP_ENABLED=false`. Turn it on when the GNAT endpoint exists and has been tested.

-----

## Phase 3 — STIX output

### 3.1 Stamping

In `sensegnat/connectors/gnat_connector.py`, when serializing a finding to STIX `indicator` or narrative to STIX `note`:

- If the finding has investigation context (from path A or path B), stamp the three custom properties.
- Stamp the companion `note` object the same way (narrative and indicator must share context or neither has it).

### 3.2 Grouping envelope

Wrap each `run_once()` output batch in a STIX `Grouping` per distinct investigation_id encountered:

- If a batch produces findings for two different investigations, emit two Groupings.
- Findings with no investigation_id are **not** wrapped in a Grouping — they go in untagged, same as today.
- Grouping `name`: `"SenseGNAT findings <run_id>"`, `context`: `"suspicious-activity"`.

-----

## Phase 4 — Telemetry adapter (GNATTelemetryAdapter)

The `GNATTelemetryAdapter` reads from the `gnat.telemetry` Kafka topic. GNAT may enrich inbound telemetry records with an investigation hint before placing them on the topic (this is GNAT-side; optional).

If the telemetry record carries a `_gnat_investigation_hint` field:

- Treat it as a strong prior for path B — skip the GNAT lookup and use the hint directly.
- Link type `"inferred"` (GNAT made the association, not SenseGNAT).

If the hint is absent, behave as before — detector fires, path B runs, etc.

This is additive — drop the field on the record, SenseGNAT ignores it.

-----

## Phase 5 — Configuration

In `sensegnat/config` (or wherever settings live):

|Setting                           |Default            |Purpose                                            |
|----------------------------------|-------------------|---------------------------------------------------|
|`investigation_lookup_enabled`    |`false`            |Master switch for path B.                          |
|`investigation_lookup_timeout_s`  |`2.0`              |Per-call timeout.                                  |
|`investigation_lookup_cache_ttl_s`|`60`               |Subject→IDs cache window.                          |
|`investigation_lookup_max_matches`|`3`                |Cap on candidate IDs listed in `"suggested"` notes.|
|`gnat_investigation_api_base_url` |(existing GNAT URL)|Derived from existing GNAT connector config.       |

All of these are safe to tune per deployment.

-----

## Phase 6 — Tests

### Unit

- `tests/test_policy_investigation.py` — rule parser accepts the new fields; rule with missing `investigation_link_type` defaults to `"confirmed"`.
- `tests/test_policy_detector_stamping.py` — `PolicyViolationDetector` emits a finding stamped with the rule’s investigation context.
- `tests/test_connector_stamping.py` — STIX `indicator` and `note` carry all three custom properties when set.
- `tests/test_grouping_envelope.py` — one Grouping per distinct investigation_id in a batch; un-tagged findings are not wrapped.
- `tests/test_subject_lookup.py` — `find_investigations_for_subject` returns `[]` on timeout, returns IDs on success, respects cache.
- `tests/test_lookup_failure_degrades.py` — when the GNAT API raises, findings still emit (unstamped). No exception propagates up.

### Integration

- `tests/integration/test_end_to_end_stamping.py` — mock GNAT API, run a full `run_once()` with a fixture that exercises path A (policy), path B (subject lookup hit), and path C (no match). Assert STIX output for each.

Keep at or above current coverage bar.

-----

## Phase 7 — Docs

- Update `README.md` “What’s implemented” with the new behaviour; mention the feature flag.
- Add `docs/how-to/attach-findings-to-investigations.md` — covers all three paths with examples.
- Add `docs/reference/investigation-context.md` — links back to canonical GNAT spec.
- Update the policy rule reference to document the two new fields.

-----

## Out of scope

- Letting SenseGNAT create investigations. GNAT owns investigation identity.
- Two-way sync of investigation state. SenseGNAT is write-only w.r.t. investigations.
- Per-investigation detector tuning. Detectors remain subject-scoped, not investigation-scoped.
- Rewriting of already-emitted findings after the fact. If the analyst later associates a finding with an investigation via the GNAT UI, that’s a GNAT-side operation and doesn’t touch SenseGNAT.

-----

## Acceptance criteria

1. A policy rule with `investigation_id` set produces findings stamped with that ID, link type `"confirmed"`.
1. With path B enabled, a detector firing on a subject that exists in an active investigation’s evidence graph produces findings stamped with that investigation’s ID, link type `"inferred"`.
1. With path B enabled and GNAT unreachable, findings still emit on time, without the custom properties. No error propagates from `run_once()`.
1. `run_once()` output wraps per-investigation findings in a `Grouping` each; untagged findings remain bare.
1. Existing tests pass unchanged. No regression in behaviour for the no-investigation-context path (which is the 95% case).

-----

## Risks

|Risk                                                                   |Mitigation                                                                                                      |
|-----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
|GNAT lookup adds latency to detector emission.                         |2s timeout, cache, feature-flag off by default.                                                                 |
|GNAT lookup cache returns stale data during long-running `run_once()`. |60s TTL is short relative to investigation lifecycle.                                                           |
|Policy rules with typo’d investigation_ids stamp findings with bad IDs.|GNAT rejects the bundle at ingest. Rule validation catches obvious format errors at load time.                  |
|A detector burst hammers the GNAT API.                                 |Cache by subject. If burst is extreme, the feature flag is the kill switch.                                     |
|Multi-match case produces confusing output.                            |Only the most recent investigation_id is stamped as “the” ID; alternatives go in a `"suggested"` note, cap at 3.|

-----

## Handoff checklist

- [ ] GNAT’s `GET /api/investigations?subject=...` endpoint exists and is tested.
- [ ] Shared contract doc is finalised in the GNAT repo.
- [ ] Confirmed in-conversation that the `sensegnat/` layout described above matches current reality.
- [ ] Feature-flag defaults agreed (lookup OFF by default until GNAT’s endpoint is production-ready).