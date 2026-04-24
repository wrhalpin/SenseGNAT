# How to attach SenseGNAT findings to GNAT investigations

SenseGNAT findings can be automatically linked to active GNAT investigations so they surface directly in the right investigation's evidence graph. There are three attachment paths. Each is independent — you can use all three at once or only the ones that fit your deployment.

---

## Path A — Declare the investigation in a policy rule (recommended)

Use this when an analyst has authored a policy rule specifically to monitor for a known threat or active case.

### YAML rule format

```yaml
subjects:
  host-finance-01:
    allowed_destinations: ["10.10.0.0/16"]
    allowed_ports: [443, 8443]
    investigation_id: "IC-2026-0042"
    investigation_link_type: "confirmed"
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `investigation_id` | No | — | The GNAT investigation ID to attach findings to |
| `investigation_link_type` | No | `"confirmed"` | `"confirmed"` when the rule was authored for this investigation; `"inferred"` is also valid |

### What happens

Any finding produced by `PolicyViolationDetector` for `host-finance-01` will carry:

```json
"x_gnat_investigation_id": "IC-2026-0042",
"x_gnat_investigation_origin": "sensegnat",
"x_gnat_investigation_link_type": "confirmed"
```

The companion `note` (narrative) gets the same three properties. GNAT then routes both objects into investigation `IC-2026-0042`'s evidence graph.

### When to use it

- You have an open investigation and want SenseGNAT to forward relevant policy violations directly into it.
- The rule was created as part of the investigation — the analyst knows exactly which subjects to watch.

---

## Path B — Subject lookup via the GNAT API

Use this when you want SenseGNAT to automatically associate behavioral findings with investigations that already reference the same subject.

### Enable the feature flag

Path B is off by default. Turn it on in your YAML config:

```yaml
investigation:
  lookup_enabled: true
  lookup_timeout_s: 2.0      # per-call timeout; never blocks detection
  lookup_cache_ttl_s: 60     # seconds to cache results per subject
  lookup_max_matches: 3      # cap on "suggested" candidates in multi-match
```

### What happens

After detectors produce findings, `SenseGNATService.run_once()` runs an enrichment pass. For each finding that doesn't already have investigation context from Path A, it calls:

```
GET /api/investigations?subject=<subject_ref>
```

- **One match** — finding is stamped with that investigation ID, link type `"inferred"`.
- **Multiple matches** — finding is stamped with the most recently updated investigation. Additional candidates are listed in a STIX `note` with link type `"suggested"`.
- **No match** — finding emits without investigation context (Path C).
- **GNAT unreachable or timeout** — finding emits without investigation context. Detection is never blocked.

### Prerequisite

GNAT must have the `GET /api/investigations?subject=...` endpoint available and tested. Until then, keep `lookup_enabled: false`.

---

## Path B (shortcut) — Telemetry hint from the Kafka stream

If GNAT enriches its Kafka telemetry records before publishing them, `GNATTelemetryAdapter` can carry the investigation hint directly into SenseGNAT without an extra API round-trip.

### Kafka record format

```json
{
  "sensor_type": "netflow",
  "src_ip": "192.168.1.10",
  "dst_ip": "10.0.0.1",
  "dst_port": 443,
  "timestamp": "2026-01-15T10:00:00+00:00",
  "_gnat_investigation_hint": "IC-2026-0042"
}
```

When `_gnat_investigation_hint` is present, SenseGNAT skips the API lookup and uses the hint directly. Link type is `"inferred"`. If `lookup_enabled` is `false`, the hint is still used — it is independent of the lookup feature flag.

---

## Path C — No context (default for general-purpose monitoring)

When a finding has no investigation context from any path, it emits as a plain STIX `indicator` without the three `x_gnat_investigation_*` properties. GNAT's own correlator may attach it to an investigation later via the GNAT UI — that is a GNAT-side operation.

This is the default for 95% of traffic. It requires no configuration.

---

## STIX Grouping envelope

When a `run_once()` batch produces findings for one or more investigations, SenseGNAT wraps the related indicators and notes in a STIX `Grouping` per distinct investigation ID:

```json
{
  "type": "grouping",
  "context": "suspicious-activity",
  "name": "SenseGNAT findings <run_id>",
  "object_refs": ["indicator--...", "note--..."],
  "x_gnat_investigation_id": "IC-2026-0042",
  "x_gnat_investigation_origin": "sensegnat"
}
```

Findings without investigation context are not wrapped — they are emitted bare.

---

## Summary: which path fires when

| Situation | Path | Link type |
|---|---|---|
| Policy rule declares `investigation_id` | A | `"confirmed"` |
| Kafka record has `_gnat_investigation_hint` | B (hint shortcut) | `"inferred"` |
| `lookup_enabled: true` and GNAT API returns a match | B | `"inferred"` |
| No context found | C | (none) |
