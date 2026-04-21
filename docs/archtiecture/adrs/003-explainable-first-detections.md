# ADR-003: Explainable detections come before advanced ML

## Status
Accepted

## Context
The first production value of SenseGNAT should be operational trust, not model novelty.

## Decision
Phase A and early Phase B detections will prioritize explainable logic such as rarity, peer deviation, time-window drift, and rule violations before introducing opaque machine learning.

## Consequences
- easier analyst adoption
- easier tuning
- clearer reporting into GNAT
- simpler testing and validation
