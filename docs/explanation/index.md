# Explanation

These documents are understanding-oriented. They discuss background, context, design decisions, and the "why" behind how SenseGNAT works. They do not tell you how to perform a task — for that, see the [Tutorials](../tutorials/) and [How-to Guides](../how-to/).

---

## Documents in this section

### [Architecture](./architecture.md)

A comprehensive overview of how SenseGNAT is structured: its role as a standalone behavioral analytics companion to GNAT, the three-layer design (ingestion, analytics, output), the complete data flow through `SenseGNATService.run_once()`, how subject identity is determined, how the policy-seeded profiling and cross-run profile accumulation work, and why STIX 2.1 is the output format.

### [Policy-Guided Baselining](./policy-guided-baselining.md)

An explanation of why SenseGNAT uses a hybrid of policy rules and observed telemetry to build behavioral baselines, rather than pure unsupervised learning or pure static rules — covering the cold-start problem, rule brittleness, how seeding works in practice, policy drift detection, and the role of peer groups in contextualizing individual behavior.

### [Explainability First](./explainability-first.md)

An explanation of SenseGNAT's commitment to transparent, human-readable detections over opaque ML scoring — covering what explainable detection means in concrete terms, why it matters for analyst trust and alert fatigue, how each detector implements explainability, the role of `NarrativeBuilder` in per-subject summaries, and an honest account of what this approach cannot catch.

---

## How explanation documents relate to the rest of the docs

Explanation documents answer the question "why does it work this way?" They are best read after completing the getting-started tutorial and before diving into how-to guides for specific tasks. If you are trying to understand a design choice you encountered in the code, start here. If you are trying to accomplish a specific task, the how-to guides will be more directly useful.

---

## Related reading

- [ADR-001](../archtiecture/adrs/001-standalone-capability.md) — Why SenseGNAT is standalone
- [ADR-002](../archtiecture/adrs/002-policy-guided-baselining.md) — Why policy seeds the baseline
- [ADR-003](../archtiecture/adrs/003-explainable-first-detections.md) — Explainability over ML
- [ADR-004](../archtiecture/adrs/004-entity-centric-data-model.md) — Entity-centric data model
- [ADR-005](../archtiecture/adrs/005-custom-behavior-objects.md) — Custom objects alongside STIX
