"""Unit tests for the domain JSON serializer (to_jsonable)."""

from __future__ import annotations

import json
from datetime import date

from campaign_planner.config import Container
from campaign_planner.domain.models import Market, PacingStrategy, PlanRequest, Vertical
from campaign_planner.domain.serialization import to_jsonable
from campaign_planner.domain.services import CampaignPlanService


def _service(container: Container) -> CampaignPlanService:
    return CampaignPlanService(
        audience=container.audience,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
    )


def test_plan_serializes_to_json(local_container: Container):
    plan = _service(local_container).build_plan(
        PlanRequest(
            objective="savings",
            market=Market.SG,
            vertical=Vertical.BANKING,
            total_budget=120_000.0,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 28),
            pacing=PacingStrategy.EVEN,
        ),
        actor="test",
    )
    payload = to_jsonable(plan)
    # Round-trips through JSON without raising (no infinities, enums -> values).
    text = json.dumps(payload)
    restored = json.loads(text)
    assert restored["market"] == "SG"
    assert restored["vertical"] == "banking"
    assert restored["requires_human_review"] is True
    # Computed rollups are present on the channel_mix.
    assert "allocated" in restored["channel_mix"]
    assert "blended_cost_per_conversion" in restored["channel_mix"]


def test_infinity_becomes_null():
    assert to_jsonable(float("inf")) is None
    assert to_jsonable(float("-inf")) is None
