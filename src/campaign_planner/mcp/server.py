"""Serve the governed tool catalog Mkt2 already declares, over MCP 2026-07-28.

The catalog declared three governed tools and served none of them: there was no MCP server
process anywhere in the fleet. This supplies the callables that answer the existing catalog and
declares nothing new. `hex_service_kit.mcpserve.bind` refuses a mismatch in either direction at
start-up.

**Two of the three tools are views onto one computation, and that is stated rather than hidden.**
`audience_segments` and `allocate_budget` are not cheaper paths than `build_plan`: the plan
service selects the segments and allocates the mix as part of building a plan, and these return
those sections of it. Pretending otherwise would let a caller think it was buying a partial
computation, and inventing separate shortcut paths would create a second way to compute a number
the plan already owns.

MCP stdio verifies no end user, so the caller is recorded as a SERVICE caller and no tenant is
asserted.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from hex_service_kit import mcpserve

from ..config import build_container
from ..domain.models import Market, PlanRequest, Vertical

#: The tools this module answers, as data, so a test can hold it against the catalog.
HANDLER_NAMES: tuple[str, ...] = ("audience_segments", "allocate_budget", "build_plan")

#: A flight window the caller did not give. The tools declare no dates, so one is chosen here
#: rather than left undefined; a quarter is the shortest window the pacing service can spread
#: over its default four legs without a leg collapsing to nothing.
_DEFAULT_FLIGHT_DAYS = 90


def _request(arguments: dict[str, Any]) -> PlanRequest:
    start = date.today()
    return PlanRequest(
        objective=str(arguments.get("objective", "") or "awareness"),
        market=Market(str(arguments.get("market", ""))),
        vertical=Vertical(str(arguments.get("vertical", ""))),
        total_budget=float(arguments.get("total_budget") or 0.0),
        start_date=start,
        end_date=start + timedelta(days=_DEFAULT_FLIGHT_DAYS),
    )


def build_handlers(actor: str) -> dict[str, mcpserve.Handler]:
    """Bind each declared tool to the plan service that already performs it."""
    from ..api.app import make_plan_service

    def build_plan(**arguments: Any) -> Any:
        return make_plan_service().build_plan(_request(arguments), actor=actor)

    def audience_segments(**arguments: Any) -> Any:
        return make_plan_service().build_plan(_request(arguments), actor=actor).segments

    def allocate_budget(**arguments: Any) -> Any:
        return make_plan_service().build_plan(_request(arguments), actor=actor).channel_mix

    return {
        "audience_segments": audience_segments,
        "allocate_budget": allocate_budget,
        "build_plan": build_plan,
    }


def build_server(actor: str, *, with_audit_tools: bool = True) -> Any:
    """Build the MCP server for Mkt2's catalog, refusing on any catalog/handler mismatch."""
    container = build_container()
    return mcpserve.build_server(
        name="campaign-planner",
        version=str(getattr(container.settings, "version", "") or "0.0.1"),
        catalog=container.tool_catalog,
        handlers=build_handlers(actor),
        audit_store=getattr(container, "audit", None) if with_audit_tools else None,
    )
