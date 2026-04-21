# ADR-005: Use custom behavior objects alongside STIX-compatible output

## Status
Accepted

## Context
STIX can represent many observables and findings, but long-lived baselines, anomaly scores, peer groups, and drift narratives do not map cleanly to stock STIX objects.

## Decision
SenseGNAT will emit STIX-compatible output where it fits and maintain custom behavior-profile, anomaly-finding, and risk-narrative objects for GNAT-native consumption.

## Consequences
- preserves interoperability where reasonable
- avoids distorting the behavior model to fit the wrong schema
- enables richer GNAT reporting
