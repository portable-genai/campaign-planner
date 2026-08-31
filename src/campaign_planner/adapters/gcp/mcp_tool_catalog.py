"""MCP tool-catalog adapter (ToolCatalogPort) — the governed tool surface for D2.

Backs the domain ``ToolCatalogPort`` by exposing D2's governed, least-privilege
capabilities as :class:`ToolSpec` objects: ``audience_segments``, ``allocate_budget`` and
``build_plan``. These are the tools the agent (or a peer agent) may invoke, each with an
explicit JSON input schema so access is scoped and auditable (least privilege).

Interop: the catalog speaks **MCP 2026-07-28**. In an ADK deployment these specs are
surfaced to the agent through an ``McpToolset`` connected to an MCP server fronting the
domain services; here the adapter only *declares* the governed catalog (declarative, no live
MCP connection required to list). The ``mcp`` package is imported LAZILY and only when an
actual MCP wire object is requested.
"""

from __future__ import annotations

from typing import Any

from ...config import Settings
from ...domain.models import ToolSpec

# MCP protocol revision this catalog conforms to.
MCP_PROTOCOL_VERSION = "2026-07-28"

# Shared schema fragment: market / vertical scoping reused across tools.
_SCOPE_SCHEMA: dict[str, Any] = {
    "market": {
        "type": "string",
        "enum": ["JP", "AU", "SG"],
        "description": "Restrict to a single market.",
    },
    "vertical": {
        "type": "string",
        "enum": ["banking", "online_retail"],
        "description": "Restrict to a single vertical.",
    },
}


# The FULL input every tool here consumes, declared once because every tool consumes all of it.
#
# All three handlers call `build_plan(_request(arguments))` and then project a slice of the
# result: `audience_segments` returns `.segments`, `allocate_budget` returns `.channel_mix`,
# `build_plan` returns the whole plan. The projection is the only difference, so a segment list
# depends on the budget and a channel mix depends on the objective exactly as much as the full
# plan does.
#
# Until 2026-08-31 the two narrow tools declared only their own headline field, with
# `additionalProperties: False`. That is not a silent default -- it is a REFUSAL: a caller who
# knew a budget shaped the segmentation could not send it, and `_request` then read
# `total_budget` as 0.0 and segmented a campaign with no money. Found mechanically by
# tests/unit/test_mcp_schema_matches_its_handler.py, which compares each declaration against
# the keys its handler actually reads.
_PLAN_INPUT_SCHEMA: dict[str, Any] = {
    "objective": {"type": "string", "description": "Campaign objective."},
    "total_budget": {"type": "number", "minimum": 1},
    **_SCOPE_SCHEMA,
}

#: Required for every tool, because every tool runs the whole plan.
_PLAN_REQUIRED = ["objective", "total_budget"]


def _build_catalog() -> dict[str, ToolSpec]:
    """Declare the governed tools with explicit, least-privilege input schemas."""
    return {
        "audience_segments": ToolSpec(
            name="audience_segments",
            description=(
                "Fetch candidate audience segments (from BigQuery) for an objective, "
                "market and vertical. Returns cited segment rows."
            ),
            input_schema={
                "type": "object",
                "properties": dict(_PLAN_INPUT_SCHEMA),
                "required": list(_PLAN_REQUIRED),
                "additionalProperties": False,
            },
        ),
        "allocate_budget": ToolSpec(
            name="allocate_budget",
            description=(
                "Allocate a total budget across channels by deterministic "
                "cost-per-conversion. Output requires human review (maker-checker)."
            ),
            input_schema={
                "type": "object",
                "properties": dict(_PLAN_INPUT_SCHEMA),
                "required": list(_PLAN_REQUIRED),
                "additionalProperties": False,
            },
        ),
        "build_plan": ToolSpec(
            name="build_plan",
            description=(
                "Build a full cited campaign plan (audience, channel mix, reach / "
                "frequency, pacing). Output requires human review before any spend."
            ),
            input_schema={
                "type": "object",
                "properties": dict(_PLAN_INPUT_SCHEMA),
                "required": list(_PLAN_REQUIRED),
                "additionalProperties": False,
            },
        ),
    }


class McpToolCatalogAdapter:
    """Declarative MCP 2026-07-28 catalog of D2's governed tools."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._catalog: dict[str, ToolSpec] = _build_catalog()

    # ------------------------------------------------------------------ #
    # ToolCatalogPort
    # ------------------------------------------------------------------ #
    def list_tools(self) -> list[ToolSpec]:
        return list(self._catalog.values())

    def get_tool(self, name: str) -> ToolSpec | None:
        return self._catalog.get(name)

    # ------------------------------------------------------------------ #
    # MCP wire helpers (lazy ``mcp`` import — only when actually used)
    # ------------------------------------------------------------------ #
    def as_mcp_tools(self) -> list[Any]:
        """Render the catalog as MCP ``Tool`` objects (MCP 2026-07-28 schema)."""
        from mcp import types as mcp_types  # noqa: PLC0415 — lazy

        # verify: https://modelcontextprotocol.io/specification/2026-07-28
        return [
            mcp_types.Tool(name=s.name, description=s.description, input_schema=s.input_schema)
            for s in self._catalog.values()
        ]
