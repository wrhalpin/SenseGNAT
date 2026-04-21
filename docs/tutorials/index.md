# Tutorials

These tutorials follow the [Diátaxis](https://diataxis.fr/) framework.
They are **learning-oriented**: each one takes you through a complete,
working experience step by step, prioritising what you learn over how much
ground is covered.

Work through them in order. Tutorial 1 gives you the foundation; Tutorial 2
builds directly on it.

---

## Available tutorials

### [01 — Getting Started](01-getting-started.md)

Install SenseGNAT, run the built-in example, read the STIX output it
produces, and trigger your first `rare-destination` finding by feeding the
pipeline two controlled event batches from an inline adapter.

### [02 — Write a Custom Adapter](02-write-a-custom-adapter.md)

Write a `JsonLinesAdapter` from scratch that reads network flow records
from a `.jsonl` log file, wire it into `SenseGNATService`, and watch a
finding fire from your own data.

---

## Before you start

- Python 3.11 or later must be installed.
- Clone the repository and run `pip install -e .` from the project root.
- No running GNAT server is required — SenseGNAT operates in record-only
  mode by default.

---

## What tutorials are not

Tutorials teach by doing. They are not reference documentation (field-by-
field API specs), how-to guides (step-by-step recipes for a specific goal
you already have), or explanations (background on why the system is
designed the way it is). For those, see the `docs/archtiecture/adrs/`
directory and the module docstrings in the source.
