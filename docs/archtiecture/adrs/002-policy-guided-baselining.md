# ADR-002: Policy seeds the baseline

## Status
Accepted

## Context
Pure static rules are too brittle for enterprise behavior analytics, while pure unsupervised learning often fails to encode what the business actually expects.

## Decision
SenseGNAT will use policy to define expected constraints and then use observed telemetry to construct and refine behavior baselines.

## Consequences
- policy drift becomes detectable
- baseline quality improves with observed reality
- operators can distinguish forbidden, expected, and merely unusual behavior
