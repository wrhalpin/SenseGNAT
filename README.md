# SenseGNAT Scaffold

This scaffold is intentionally lightweight. It establishes the package boundaries and contracts for a Phase A implementation without pretending to be a finished analytics engine.

## Package boundaries

- `sensegnat.ingestion`  
  source adapters and normalized event contracts

- `sensegnat.models`  
  entity and finding models

- `sensegnat.behavior`  
  profile construction and baseline state

- `sensegnat.detection`  
  explainable detectors

- `sensegnat.connectors`  
  GNAT integration contract

- `sensegnat.config`  
  runtime configuration

- `sensegnat.storage`  
  profile and finding persistence interfaces

- `sensegnat.api`  
  service surface for reporting, queries, and health

## Phase A implementation target

Wire a single source adapter, implement baseline rarity, and emit a simple finding set through the GNAT connector contract.
