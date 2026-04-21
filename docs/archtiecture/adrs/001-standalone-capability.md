# ADR-001: SenseGNAT remains a standalone capability

## Status
Accepted

## Context
GNAT already occupies the role of abstraction and orchestration layer across many platforms. Adding stateful behavior analytics directly into GNAT core would blur boundaries, increase runtime complexity, and make connector and reporting concerns compete with analytics concerns.

## Decision
SenseGNAT will be implemented as a standalone product that integrates into GNAT through a connector and shared object model rather than as a GNAT core module.

## Consequences
Positive:

- keeps GNAT core clean
- allows analytics-specific storage and scheduling decisions
- reduces risk of forcing all GNAT deployments to carry telemetry-heavy behavior analytics dependencies
- supports independent release cadence

Tradeoffs:

- requires connector, schema, and lifecycle coordination
- introduces another deployable component
