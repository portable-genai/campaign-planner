"""Serve the governed tool catalog campaign-planner already declares, over MCP 2026-07-28.

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

from ..adapters.controls import RecordingReviewRouter
from ..config import build_container
from ..domain.models import Market, Plan, PlanRequest, Vertical
from ..domain.serialization import to_jsonable

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
    """Bind each declared tool to the plan service that already performs it.

    Every tool builds a plan, and every plan is handed to the review router, so each goes
    through :class:`RecordingReviewRouter`: a failed hand-off is logged by exception type rather
    than swallowed. ``build_plan`` returns the whole plan and so also says what happened to the
    hand-off (``review_routing``); the two section tools return a section, which has no place
    for it.
    """
    from ..api.deps import get_container, make_plan_service

    def plan_for(arguments: dict[str, Any]) -> tuple[Plan, RecordingReviewRouter]:
        routing = RecordingReviewRouter(get_container().review_router)
        plan = make_plan_service(review_router=routing).build_plan(_request(arguments), actor=actor)
        return plan, routing

    def build_plan(**arguments: Any) -> Any:
        plan, routing = plan_for(arguments)
        payload: dict[str, Any] = to_jsonable(plan)
        payload["review_routing"] = routing.outcome.value
        return payload

    def audience_segments(**arguments: Any) -> Any:
        return plan_for(arguments)[0].segments

    def allocate_budget(**arguments: Any) -> Any:
        return plan_for(arguments)[0].channel_mix

    return {
        "audience_segments": audience_segments,
        "allocate_budget": allocate_budget,
        "build_plan": build_plan,
    }


def build_server(actor: str, *, with_audit_tools: bool = True) -> Any:
    """Build the MCP server for campaign-planner's catalog, refusing on any catalog/handler
    mismatch.
    """
    container = build_container()
    return mcpserve.build_server(
        name="campaign-planner",
        version=str(getattr(container.settings, "version", "") or "0.0.1"),
        catalog=container.tool_catalog,
        handlers=build_handlers(actor),
        audit_store=getattr(container, "audit", None) if with_audit_tools else None,
    )
