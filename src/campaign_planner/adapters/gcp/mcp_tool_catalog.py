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
                "properties": {
                    "objective": {"type": "string", "description": "Campaign objective."},
                    **_SCOPE_SCHEMA,
                },
                "required": ["objective"],
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
                "properties": {
                    "total_budget": {"type": "number", "minimum": 1},
                    **_SCOPE_SCHEMA,
                },
                "required": ["total_budget"],
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
                "properties": {
                    "objective": {"type": "string"},
                    "total_budget": {"type": "number", "minimum": 1},
                    **_SCOPE_SCHEMA,
                },
                "required": ["objective", "total_budget"],
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
            mcp_types.Tool(name=s.name, description=s.description, inputSchema=s.input_schema)
            for s in self._catalog.values()
        ]
