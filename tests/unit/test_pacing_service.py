"""Unit tests for the deterministic PacingService (flight-schedule builder)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from campaign_planner.domain.errors import InvalidFlightError
from campaign_planner.domain.models import Market, PacingStrategy, Vertical
from campaign_planner.domain.pacing_service import PacingService

START = date(2026, 7, 1)
END = date(2026, 7, 28)


def _build(strategy: PacingStrategy, legs: int = 4, budget: float = 100_000.0):
    return PacingService().build(START, END, legs, budget, strategy, Market.SG, Vertical.BANKING)


def test_legs_sum_to_total_budget_even():
    fs = _build(PacingStrategy.EVEN)
    assert abs(fs.paced_total - 100_000.0) <= 0.01


def test_legs_sum_to_total_budget_front_loaded():
    fs = _build(PacingStrategy.FRONT_LOADED)
    assert abs(fs.paced_total - 100_000.0) <= 0.01


def test_legs_sum_to_total_budget_back_loaded():
    fs = _build(PacingStrategy.BACK_LOADED)
    assert abs(fs.paced_total - 100_000.0) <= 0.01


def test_even_pacing_has_equal_weights():
    fs = _build(PacingStrategy.EVEN)
    weights = [leg.weight for leg in fs.legs]
    assert max(weights) - min(weights) < 0.01


def test_front_loaded_is_decreasing():
    fs = _build(PacingStrategy.FRONT_LOADED)
    amounts = [leg.amount for leg in fs.legs]
    assert amounts[0] > amounts[-1]


def test_back_loaded_is_increasing():
    fs = _build(PacingStrategy.BACK_LOADED)
    amounts = [leg.amount for leg in fs.legs]
    assert amounts[0] < amounts[-1]


def test_legs_are_contiguous_and_cover_window():
    fs = _build(PacingStrategy.EVEN, legs=4)
    assert fs.legs[0].start_date == START.isoformat()
    assert fs.legs[-1].end_date == END.isoformat()
    # Each leg starts the day after the previous ends.
    for prev, nxt in zip(fs.legs, fs.legs[1:], strict=False):
        assert date.fromisoformat(nxt.start_date) == date.fromisoformat(prev.end_date) + timedelta(
            days=1
        )


def test_single_leg_takes_whole_window_and_budget():
    fs = _build(PacingStrategy.FRONT_LOADED, legs=1)
    assert len(fs.legs) == 1
    assert fs.legs[0].start_date == START.isoformat()
    assert fs.legs[0].end_date == END.isoformat()
    assert abs(fs.legs[0].amount - 100_000.0) <= 0.01


def test_end_before_start_raises():
    with pytest.raises(InvalidFlightError):
        PacingService().build(
            END, START, 4, 100_000.0, PacingStrategy.EVEN, Market.SG, Vertical.BANKING
        )


def test_zero_legs_raises():
    with pytest.raises(InvalidFlightError):
        PacingService().build(
            START, END, 0, 100_000.0, PacingStrategy.EVEN, Market.SG, Vertical.BANKING
        )


def test_legs_capped_at_window_days_no_inverted_ranges():
    # A 1-day window cannot host 4 legs: legs must be capped at the number of days, and no
    # leg may extend past end_date or have an inverted (end-before-start) date range.
    one_day = date(2026, 7, 1)
    fs = PacingService().build(
        one_day, one_day, 4, 100_000.0, PacingStrategy.EVEN, Market.SG, Vertical.BANKING
    )
    assert len(fs.legs) == 1
    for leg in fs.legs:
        s = date.fromisoformat(leg.start_date)
        e = date.fromisoformat(leg.end_date)
        assert s <= e
        assert s >= one_day
        assert e <= one_day
    assert abs(fs.paced_total - 100_000.0) <= 0.01


def test_legs_capped_at_window_days_three_day_window():
    # 3-day window, 5 requested legs -> capped to 3 contiguous one-day legs covering the window.
    start, end = date(2026, 7, 1), date(2026, 7, 3)
    fs = PacingService().build(
        start, end, 5, 90_000.0, PacingStrategy.EVEN, Market.SG, Vertical.BANKING
    )
    assert len(fs.legs) == 3
    assert fs.legs[0].start_date == start.isoformat()
    assert fs.legs[-1].end_date == end.isoformat()
    for prev, nxt in zip(fs.legs, fs.legs[1:], strict=False):
        assert date.fromisoformat(nxt.start_date) == date.fromisoformat(prev.end_date) + timedelta(
            days=1
        )
    assert abs(fs.paced_total - 90_000.0) <= 0.01


def test_pacing_is_deterministic():
    a = _build(PacingStrategy.FRONT_LOADED)
    b = _build(PacingStrategy.FRONT_LOADED)
    assert a == b
