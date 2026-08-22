"""ADK FunctionTools that expose the D2 domain services to the agent.

Each tool is a thin, side-effect-honest wrapper: it builds the relevant domain service from a
:class:`~campaign_planner.config.Container` (so every port is bound to the adapter selected by
the active profile), invokes one domain method, and returns a JSON-safe dict via
:func:`~campaign_planner.domain.serialization.to_jsonable`.

Design notes
------------
* The domain services own orchestration and every consequential number (audience selection,
  deterministic channel-mix / budget allocation, reach & frequency, pacing; SPEC §5). These
  tools add **no** business logic of their own: the model decides *which* artifact to produce,
  the service decides *how* and owns the maths (the LLM only narrates the brief / calendar).
* ``google.adk`` is imported lazily inside :func:`build_function_tools` so this module imports
  cleanly under the on-prem / local / test profile with no ADK installed (SPEC §4). The plain
  Python tool callables are importable and unit-testable without ADK at all.
* Every callable carries a precise type-hinted signature and docstring: ADK derives the
  tool's name, description and JSON parameter schema from them.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from ..config import Container, Settings, build_container

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

_DEFAULT_ACTOR = "campaign-planner-agent"
_DEFAULT_FLIGHT_DAYS = 90


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _parse_date(value: str, default: date) -> date:
    if not value:
        return default
    return date.fromisoformat(value)


def build_campaign_plan(
    objective: str,
    total_budget: float,
    market: str = "SG",
    vertical: str = "banking",
    start_date: str = "",
    end_date: str = "",
    flight_legs: int = 4,
    pacing: str = "even",
    max_segments: int = 5,
    actor: str = _DEFAULT_ACTOR,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Turn an objective and budget into a full cited campaign plan.

    Runs the pipeline (audience segmentation and selection, deterministic channel-mix and
    budget allocation, reach & frequency, pacing, plus a narrated brief and calendar) and
    returns a ``Plan``. Always flagged for human review (maker-checker); every consequential
    figure carries a citation and is computed deterministically, never by the model.

    Args:
      objective: The campaign objective, e.g. "savings account acquisition".
      total_budget: Total budget in the market currency (> 0).
      market: Market code: "JP", "AU" or "SG".
      vertical: "banking" or "online_retail".
      start_date: Flight start date, ISO "YYYY-MM-DD" (defaults to today).
      end_date: Flight end date, ISO "YYYY-MM-DD" (defaults to start + 90 days).
      flight_legs: Number of pacing legs.
      pacing: "even", "front_loaded" or "back_loaded".
      max_segments: Maximum audience segments to target.
      actor: Authenticated identity the request is made for.

    Returns:
      A JSON-safe ``Plan`` dict.
    """
    from ..api.deps import make_plan_service
    from ..domain.models import Market, PacingStrategy, PlanRequest, Vertical
    from ..domain.serialization import to_jsonable

    c = _container(settings)
    start = _parse_date(start_date, date.today())
    end = _parse_date(end_date, start + timedelta(days=_DEFAULT_FLIGHT_DAYS))
    request = PlanRequest(
        objective=objective,
        market=Market(market),
        vertical=Vertical(vertical),
        total_budget=total_budget,
        start_date=start,
        end_date=end,
        flight_legs=flight_legs,
        pacing=PacingStrategy(pacing),
        max_segments=max_segments,
        channels=(),
    )
    return to_jsonable(make_plan_service(c).build_plan(request, actor=actor))


def select_audience(
    objective: str,
    market: str = "SG",
    vertical: str = "banking",
    max_segments: int = 5,
    actor: str = _DEFAULT_ACTOR,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Select and rank the target audience segments for an objective.

    Returns the top ``max_segments`` consented, reachable segments (propensity- and
    value-ranked) for the objective, market and vertical. This is an input to a plan, not a
    consequential output, so it is not maker-checker gated on its own.

    Args:
      objective: The campaign objective, e.g. "credit-card cross-sell".
      market: Market code: "JP", "AU" or "SG".
      vertical: "banking" or "online_retail".
      max_segments: Maximum audience segments to return.
      actor: Authenticated identity the request is made for.

    Returns:
      A JSON-safe dict with the ranked ``segments``.
    """
    from ..api.deps import make_audience_selection_service
    from ..domain.models import Market, Vertical
    from ..domain.serialization import to_jsonable

    c = _container(settings)
    segments = c.audience.segments(objective, Market(market), Vertical(vertical))
    selected = make_audience_selection_service(c).select(segments, max_segments=max_segments)
    return to_jsonable({"objective": objective, "market": market, "segments": selected})


TOOL_FUNCTIONS = (
    build_campaign_plan,
    select_audience,
)


def governed_tool_names() -> frozenset[str]:
    """The tool names this agent exposes (mirrors the governed MCP catalog, rule R4)."""
    return frozenset(fn.__name__ for fn in TOOL_FUNCTIONS)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each domain-service callable as an ADK ``FunctionTool``.

    ADK introspects each function's signature and docstring to derive the tool name,
    description and parameter JSON schema. ``google.adk`` is imported here (lazily) so the
    module is import-safe without ADK installed (SPEC §4).
    """
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=fn) for fn in TOOL_FUNCTIONS]
