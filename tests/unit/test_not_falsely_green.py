"""Prove every eval metric can go RED: a degraded plan must score below its threshold.

A metric that cannot fail proves nothing, so each scorer in ``eval/run_eval.py`` is fed the
SAME plan twice: once as the pipeline built it (green) and once with exactly the defect the
metric exists to catch (red). The scorers are imported from the eval module rather than
re-implemented here, so a scorer that silently became a constant 1.0 breaks this build.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from agent_eval_kit import assert_can_go_red
from eval.run_eval import (
    THRESHOLDS,
    _make_service,
    score_budget_accuracy,
    score_citation_accuracy,
    score_groundedness,
    score_review_safety,
)

from campaign_planner.domain.models import Market, Plan, PlanRequest, Vertical

_ACTOR = "eval@bank.example"


@pytest.fixture(scope="module")
def plan() -> Plan:
    """One real plan off the local (SDK-free) stack: the green case for every metric."""
    return _make_service().build_plan(
        PlanRequest(
            objective="savings account acquisition",
            market=Market.SG,
            vertical=Vertical.BANKING,
            total_budget=120_000.0,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 28),
        ),
        actor=_ACTOR,
    )


def test_plan_groundedness_can_go_red(plan: Plan) -> None:
    assert_can_go_red(
        score_groundedness,
        green=plan,
        red=replace(plan, citations=()),  # an allocation with nothing behind it
        threshold=THRESHOLDS["plan_groundedness"],
        metric="plan_groundedness",
    )


def test_citation_accuracy_can_go_red(plan: Plan) -> None:
    fabricated = replace(plan.citations[0], source_id="fabricated-source-not-in-evidence")
    assert_can_go_red(
        score_citation_accuracy,
        green=plan,
        red=replace(plan, citations=(fabricated,)),  # cites a source the plan never derived
        threshold=THRESHOLDS["citation_accuracy"],
        metric="citation_accuracy",
    )


def test_budget_accuracy_can_go_red(plan: Plan) -> None:
    assert_can_go_red(
        score_budget_accuracy,
        green=plan,
        red=replace(plan, total_budget=plan.total_budget * 2),  # allocation stops reconciling
        threshold=THRESHOLDS["budget_accuracy"],
        metric="budget_accuracy",
    )


def test_review_safety_can_go_red(plan: Plan) -> None:
    assert_can_go_red(
        score_review_safety,
        green=plan,
        red=replace(plan, requires_human_review=False),  # the human gate quietly dropped
        threshold=THRESHOLDS["review_safety"],
        metric="review_safety",
    )
