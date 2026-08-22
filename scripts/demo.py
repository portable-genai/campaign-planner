#!/usr/bin/env python3
"""Offline synthetic-data demo for D2 (audit-first).

Runs the real ``CampaignPlanService`` over the local (offline) adapters for a few
(vertical, market) pairs, prints a readable, cited trace to stdout, and writes the plan
audit views to ``scripts/out/*.json`` for the dependency-free renderer / screenshots. It is
also the end-to-end smoke test for the slice: deterministic, so screenshots never drift.

Usage::

    MKT_CAMPAIGN_PROFILE=local python scripts/demo.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from campaign_planner.api.deps import make_plan_service
from campaign_planner.config import Container, LocalSettings, Settings
from campaign_planner.domain.models import Market, PacingStrategy, PlanRequest, Vertical
from campaign_planner.domain.serialization import to_jsonable
from campaign_planner.domain.services import CampaignPlanService

_OUT = Path(__file__).resolve().parent / "out"
_START = date(2026, 7, 1)
_END = date(2026, 7, 28)

# (objective, market, vertical, budget, pacing) — both verticals across JP/AU/SG.
_SCENARIOS = [
    ("savings account acquisition", Market.SG, Vertical.BANKING, 120_000.0, PacingStrategy.EVEN),
    (
        "multi-currency wallet launch",
        Market.JP,
        Vertical.BANKING,
        200_000.0,
        PacingStrategy.FRONT_LOADED,
    ),
    ("loyalty programme push", Market.JP, Vertical.ONLINE_RETAIL, 90_000.0, PacingStrategy.EVEN),
    (
        "seasonal sale campaign",
        Market.AU,
        Vertical.ONLINE_RETAIL,
        110_000.0,
        PacingStrategy.BACK_LOADED,
    ),
]


def _service() -> CampaignPlanService:
    base = Settings.load("config/settings.yaml")
    settings = Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        models=base.models,
        bigquery=base.bigquery,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(audit_path=":memory:"),
        policy=base.policy,
        markets=base.markets,
        adapters=base.adapters,
    )
    return make_plan_service(Container(settings))


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    service = _service()
    for objective, market, vertical, budget, pacing in _SCENARIOS:
        request = PlanRequest(
            objective=objective,
            market=market,
            vertical=vertical,
            total_budget=budget,
            start_date=_START,
            end_date=_END,
            pacing=pacing,
        )
        plan = service.build_plan(request, actor="demo")
        print("=" * 78)
        print(f"PLAN: {objective}  [{market.value}/{vertical.value}]")
        print(f"  review required : {plan.requires_human_review}")
        print(
            f"  budget          : {plan.total_budget:,.0f}  allocated: {plan.channel_mix.allocated:,.0f}"
        )
        print(f"  segments        : {len(plan.segments)}")
        for line in plan.channel_mix.lines:
            print(
                f"  channel {line.channel.value:8s}: {line.amount:>10,.0f} "
                f"({line.share * 100:4.0f}%)  {line.expected_conversions:>8,.0f} conv"
            )
        rf = plan.reach_frequency
        print(f"  reach           : {rf.unique_reach:,} unique ({rf.reach_pct * 100:.1f}%)")
        print(
            f"  flight legs     : {len(plan.flight_schedule.legs)} ({plan.flight_schedule.strategy.value})"
        )
        print(f"  citations       : {len(plan.citations)}")
        out_path = _OUT / f"{plan.id}.json"
        out_path.write_text(json.dumps(to_jsonable(plan), indent=2), encoding="utf-8")
        print(f"  wrote           : {out_path}")
    print("=" * 78)
    print("Demo complete. Audit views written to scripts/out/ (obviously-fictional data).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
