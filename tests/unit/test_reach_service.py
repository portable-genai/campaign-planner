"""Unit tests for the deterministic ReachFrequencyService."""

from __future__ import annotations

from campaign_planner.domain.models import BudgetLine, Channel, ChannelMix, Market, Vertical
from campaign_planner.domain.reach_service import ReachFrequencyService


def _line(channel: Channel, impressions: int, reach: int) -> BudgetLine:
    return BudgetLine(
        channel=channel,
        amount=10_000.0,
        share=0.5,
        expected_impressions=impressions,
        expected_reach=reach,
        expected_conversions=100.0,
        expected_cost_per_conversion=100.0,
    )


def _mix(*lines: BudgetLine) -> ChannelMix:
    return ChannelMix(
        market=Market.SG, vertical=Vertical.BANKING, total_budget=20_000.0, lines=lines
    )


def test_unique_reach_never_exceeds_addressable():
    svc = ReachFrequencyService()
    mix = _mix(_line(Channel.SEARCH, 900_000, 300_000))
    rf = svc.estimate(mix, addressable=100_000, market=Market.SG, vertical=Vertical.BANKING)
    assert rf.unique_reach <= 100_000


def test_combined_reach_below_naive_sum_with_overlap():
    svc = ReachFrequencyService()
    mix = _mix(
        _line(Channel.SEARCH, 300_000, 60_000),
        _line(Channel.SOCIAL, 300_000, 60_000),
    )
    rf = svc.estimate(mix, addressable=100_000, market=Market.SG, vertical=Vertical.BANKING)
    # Naive sum would be 120_000 but it is capped/de-duplicated below addressable.
    assert rf.unique_reach < 120_000
    assert rf.unique_reach <= 100_000


def test_average_frequency_is_impressions_over_reach():
    svc = ReachFrequencyService()
    mix = _mix(_line(Channel.SEARCH, 300_000, 50_000))
    rf = svc.estimate(mix, addressable=100_000, market=Market.SG, vertical=Vertical.BANKING)
    assert rf.average_frequency > 0
    assert abs(rf.average_frequency - rf.impressions / rf.unique_reach) < 0.01


def test_effective_reach_below_unique_reach():
    svc = ReachFrequencyService()
    mix = _mix(_line(Channel.SEARCH, 300_000, 50_000))
    rf = svc.estimate(mix, addressable=100_000, market=Market.SG, vertical=Vertical.BANKING)
    assert rf.effective_reach <= rf.unique_reach


def test_zero_addressable_yields_zero_reach():
    svc = ReachFrequencyService()
    mix = _mix(_line(Channel.SEARCH, 100_000, 50_000))
    rf = svc.estimate(mix, addressable=0, market=Market.SG, vertical=Vertical.BANKING)
    assert rf.unique_reach == 0
    assert rf.effective_reach == 0


def test_reach_pct_is_fraction():
    svc = ReachFrequencyService()
    mix = _mix(_line(Channel.SEARCH, 150_000, 40_000))
    rf = svc.estimate(mix, addressable=100_000, market=Market.SG, vertical=Vertical.BANKING)
    assert 0.0 <= rf.reach_pct <= 1.0


def test_reach_is_deterministic():
    svc = ReachFrequencyService()
    mix = _mix(_line(Channel.SEARCH, 300_000, 50_000))
    a = svc.estimate(mix, 100_000, Market.SG, Vertical.BANKING)
    b = svc.estimate(mix, 100_000, Market.SG, Vertical.BANKING)
    assert a == b
