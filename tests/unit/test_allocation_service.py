"""Unit tests for the deterministic BudgetAllocationService (channel-mix optimiser)."""

from __future__ import annotations

import pytest

from campaign_planner.domain.allocation_service import BudgetAllocationService
from campaign_planner.domain.errors import InvalidBudgetError, NoChannelBenchmarkError
from campaign_planner.domain.models import Channel, ChannelBenchmark, Market, Vertical


def _bm(
    channel: Channel,
    cpm: float,
    ctr: float,
    conv: float,
    max_reach: int,
    min_spend: float = 0.0,
) -> ChannelBenchmark:
    return ChannelBenchmark(
        channel=channel,
        market=Market.SG,
        vertical=Vertical.BANKING,
        cpm=cpm,
        ctr=ctr,
        conversion_rate=conv,
        max_reach=max_reach,
        min_spend=min_spend,
    )


def test_allocation_reconciles_to_total_budget():
    svc = BudgetAllocationService()
    benchmarks = (
        _bm(Channel.SEARCH, 9.0, 0.045, 0.06, 120_000),
        _bm(Channel.SOCIAL, 6.0, 0.012, 0.02, 400_000),
    )
    mix = svc.allocate(100_000.0, benchmarks, Market.SG, Vertical.BANKING)
    assert abs(mix.allocated - 100_000.0) <= 0.05
    assert abs(sum(line.share for line in mix.lines) - 1.0) <= 0.01


def test_allocation_prefers_more_efficient_channel():
    svc = BudgetAllocationService()
    # SEARCH has far lower cost-per-conversion than DISPLAY.
    efficient = _bm(Channel.SEARCH, 9.0, 0.045, 0.06, 10_000_000)
    inefficient = _bm(Channel.DISPLAY, 3.5, 0.004, 0.008, 10_000_000)
    mix = svc.allocate(100_000.0, (inefficient, efficient), Market.SG, Vertical.BANKING)
    by_channel = {line.channel: line.amount for line in mix.lines}
    assert by_channel[Channel.SEARCH] > by_channel.get(Channel.DISPLAY, 0.0)


def test_allocation_respects_channel_cap():
    svc = BudgetAllocationService(saturation_frequency=3.0)
    small = _bm(Channel.PARTNER, 7.5, 0.02, 0.04, 1_000)  # tiny reach => low cap
    big = _bm(Channel.SOCIAL, 6.0, 0.012, 0.02, 5_000_000)
    mix = svc.allocate(500_000.0, (small, big), Market.SG, Vertical.BANKING)
    partner = next((line for line in mix.lines if line.channel is Channel.PARTNER), None)
    assert partner is not None
    # Partner reach is capped at its max_reach.
    assert partner.expected_reach <= 1_000


def test_allocation_honours_min_spend_floor():
    svc = BudgetAllocationService()
    floor_channel = _bm(Channel.PARTNER, 7.5, 0.001, 0.001, 90_000, min_spend=5_000.0)
    efficient = _bm(Channel.SEARCH, 9.0, 0.045, 0.06, 10_000_000)
    mix = svc.allocate(100_000.0, (floor_channel, efficient), Market.SG, Vertical.BANKING)
    partner = next(line for line in mix.lines if line.channel is Channel.PARTNER)
    assert partner.amount >= 5_000.0 - 0.01


def test_zero_budget_raises():
    svc = BudgetAllocationService()
    with pytest.raises(InvalidBudgetError):
        svc.allocate(
            0.0, (_bm(Channel.SEARCH, 9.0, 0.045, 0.06, 1000),), Market.SG, Vertical.BANKING
        )


def test_floors_exceeding_budget_raise():
    svc = BudgetAllocationService()
    floor = _bm(Channel.PARTNER, 7.5, 0.02, 0.04, 90_000, min_spend=50_000.0)
    with pytest.raises(InvalidBudgetError):
        svc.allocate(10_000.0, (floor,), Market.SG, Vertical.BANKING)


def test_no_benchmarks_raises():
    svc = BudgetAllocationService()
    with pytest.raises(NoChannelBenchmarkError):
        svc.allocate(100_000.0, (), Market.SG, Vertical.BANKING)


def test_channel_filter_restricts_allocation():
    svc = BudgetAllocationService()
    benchmarks = (
        _bm(Channel.SEARCH, 9.0, 0.045, 0.06, 10_000_000),
        _bm(Channel.SOCIAL, 6.0, 0.012, 0.02, 10_000_000),
    )
    mix = svc.allocate(
        100_000.0, benchmarks, Market.SG, Vertical.BANKING, channels=(Channel.SEARCH,)
    )
    assert {line.channel for line in mix.lines} == {Channel.SEARCH}


def test_allocation_is_deterministic():
    svc = BudgetAllocationService()
    benchmarks = (
        _bm(Channel.SEARCH, 9.0, 0.045, 0.06, 120_000),
        _bm(Channel.SOCIAL, 6.0, 0.012, 0.02, 400_000),
    )
    a = svc.allocate(100_000.0, benchmarks, Market.SG, Vertical.BANKING)
    b = svc.allocate(100_000.0, benchmarks, Market.SG, Vertical.BANKING)
    assert [(line.channel, line.amount) for line in a.lines] == [
        (line.channel, line.amount) for line in b.lines
    ]


def test_requires_human_review_is_true():
    svc = BudgetAllocationService()
    mix = svc.allocate(
        100_000.0,
        (_bm(Channel.SEARCH, 9.0, 0.045, 0.06, 120_000),),
        Market.SG,
        Vertical.BANKING,
    )
    assert mix.requires_human_review is True
