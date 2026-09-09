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
    _make_service,
    load_thresholds_from_rubrics,
    score_budget_accuracy,
    score_citation_accuracy,
    score_groundedness,
    score_review_safety,
)

from campaign_planner.domain.models import Market, Plan, PlanRequest, Vertical

#: The reviewed bars, read from `eval/rubrics/*.yaml` exactly as the gate reads them. The
#: module-level dict this used to import is gone: having both was two homes for one number.
THRESHOLDS = load_thresholds_from_rubrics()

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


def test_allocation_correctness_can_go_red_in_both_directions(plan: Plan) -> None:
    """Spend on an unpriced channel, and a single-channel plan, are different failures.

    budget_accuracy cannot see either: totals reconcile however the money is split. A one-sided
    proof would certify whichever half it did not exercise.
    """
    from dataclasses import replace as _replace
    from types import SimpleNamespace

    from eval.run_eval import benchmarked_channels, score_allocation_correctness

    benchmarks = benchmarked_channels()
    # The golden case this plan corresponds to, as the runner's loader would present it.
    example = SimpleNamespace(market="SG", vertical="banking")
    priced = benchmarks[("SG", "banking")]
    assert score_allocation_correctness(plan, example, benchmarks) == 1.0

    # One channel only: the mix a cost-minimising allocator produces when nothing stops it.
    single = _replace(
        plan,
        channel_mix=_replace(plan.channel_mix, lines=(plan.channel_mix.lines[0],)),
    )
    assert score_allocation_correctness(single, example, benchmarks) < 1.0

    # A channel nobody published a cost for: the eval's own benchmark table, minus one channel
    # the plan actually used, which is the shape of a benchmark table drifting from the mix.
    drifted = dict(benchmarks)
    drifted[(example.market, example.vertical)] = set(list(priced)[:-1]) - {
        plan.channel_mix.lines[0].channel.value
    }
    assert score_allocation_correctness(plan, example, drifted) < 1.0


def test_every_scored_metric_has_a_reviewed_bar_and_every_bar_is_scored() -> None:
    """Both directions. The second is the one nobody writes by hand, and the one that rots."""
    from agent_eval_kit import load_rubrics
    from agent_eval_kit.rubrics import RubricError
    from eval.run_eval import RUBRICS, SCORED

    load_rubrics(RUBRICS).assert_covers(SCORED)
    with pytest.raises(RubricError, match="reads as governance"):
        load_rubrics(RUBRICS).assert_covers(SCORED[:-1])
