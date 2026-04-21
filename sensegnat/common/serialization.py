from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any


def to_dict(obj: Any) -> Any:
    """Recursively convert a frozen dataclass to a JSON-serialisable structure.

    - dataclass instance  →  dict (field name → to_dict(value))
    - datetime            →  ISO 8601 string
    - frozenset / set     →  sorted list
    - list / tuple        →  list
    - dict                →  dict with values recursed
    - everything else     →  unchanged
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (frozenset, set)):
        return sorted(to_dict(v) for v in obj)
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj
