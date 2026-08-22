"""JSON-safe serialization for domain objects.

``to_jsonable(obj)`` converts dataclasses, enums, datetimes and nested containers into
plain JSON-serializable Python (``dict`` / ``list`` / ``str`` / ``int`` / ``float`` /
``bool`` / ``None``). Used by the audit sink, the remote-platform clients and the API /
HTML renderer to serialize a campaign plan.

Rules:
* ``enum.Enum``  -> ``.value``
* ``datetime``   -> ``.isoformat()``
* dataclass      -> ``{field: to_jsonable(value)}`` (recursively), plus selected
                    ``@property`` rollups so the JSON carries the computed figures
* tuple / list   -> ``[to_jsonable(x), ...]`` (tuples become lists for JSON)
* dict           -> ``{to_key(k): to_jsonable(v)}`` (enum keys -> ``.value``)
* ``float('inf')`` -> ``None`` (JSON has no infinity)

Pure standard library; no Google Cloud, ADK, or framework imports.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from datetime import date, datetime
from typing import Any

# dataclass type name -> tuple of computed @property names to include in the JSON, so the
# renderer / UI can show the rollups (allocated, blended CAC, ...) without recomputation.
_COMPUTED_PROPERTIES: dict[str, tuple[str, ...]] = {
    "ChannelMix": (
        "allocated",
        "expected_conversions",
        "expected_reach",
        "blended_cost_per_conversion",
        "requires_human_review",
    ),
    "ChannelBenchmark": ("cost_per_conversion",),
    "AudienceSegment": ("consented_reachable",),
    "ReachFrequency": ("reach_pct",),
    "FlightSchedule": ("paced_total",),
}


def _jsonable_key(key: Any) -> str:
    """Coerce a mapping key into a JSON object key (always a string)."""
    if isinstance(key, enum.Enum):
        return str(key.value)
    return str(key)


def to_jsonable(obj: Any) -> Any:
    """Recursively convert ``obj`` into JSON-serializable Python.

    Unknown objects fall back to ``str(obj)`` so serialization never raises on an
    unexpected type at an audit / serialization boundary.
    """
    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, (int,)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, str):
        return obj
    if isinstance(obj, enum.Enum):
        return to_jsonable(obj.value)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).decode("utf-8", errors="replace")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        for prop in _COMPUTED_PROPERTIES.get(type(obj).__name__, ()):
            out[prop] = to_jsonable(getattr(obj, prop))
        return out
    if isinstance(obj, dict):
        return {_jsonable_key(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(x) for x in obj]
    return str(obj)
