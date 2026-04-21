# ADR-004: Use an entity-centric data model

## Status
Accepted

## Context
Raw events do not explain behavior by themselves. Analysts reason about users, hosts, services, and relationships.

## Decision
SenseGNAT will maintain profiles and relationships around canonical entities and derive detections from entity behavior over time.

## Consequences
- better narratives
- better hunting
- more stable abstractions for connector output
