"""Unit tests for the deterministic AudienceSelectionService."""

from __future__ import annotations

from campaign_planner.domain.audience_service import AudienceSelectionService
from campaign_planner.domain.models import AudienceSegment, Market, Vertical


def _seg(
    sid: str, propensity: float, value: float, consent: float, reachable: int = 100_000
) -> AudienceSegment:
    return AudienceSegment(
        id=sid,
        name=sid,
        market=Market.SG,
        vertical=Vertical.BANKING,
        size=reachable * 2,
        reachable_size=reachable,
        propensity=propensity,
        expected_value=value,
        consent_rate=consent,
    )


def test_select_ranks_by_score_descending():
    svc = AudienceSelectionService()
    segments = (
        _seg("low", 0.1, 50, 0.9),
        _seg("high", 0.5, 200, 0.9),
        _seg("mid", 0.3, 100, 0.9),
    )
    selected = svc.select(segments, max_segments=3)
    assert [s.segment.id for s in selected] == ["high", "mid", "low"]
    assert [s.rank for s in selected] == [1, 2, 3]
    # scores are non-increasing
    assert selected[0].score >= selected[1].score >= selected[2].score


def test_select_caps_at_max_segments():
    svc = AudienceSelectionService()
    segments = tuple(_seg(f"s{i}", 0.3, 100, 0.9) for i in range(10))
    assert len(svc.select(segments, max_segments=3)) == 3


def test_select_drops_zero_consent_segments():
    svc = AudienceSelectionService(min_consent=0.0)
    segments = (
        _seg("nobody", 0.9, 200, 0.0),  # zero consent => zero consented-reachable
        _seg("real", 0.3, 100, 0.8),
    )
    selected = svc.select(segments)
    assert [s.segment.id for s in selected] == ["real"]


def test_select_respects_consent_floor():
    svc = AudienceSelectionService(min_consent=0.75)
    segments = (
        _seg("toolow", 0.9, 200, 0.5),
        _seg("ok", 0.3, 100, 0.8),
    )
    selected = svc.select(segments)
    assert [s.segment.id for s in selected] == ["ok"]


def test_select_is_deterministic():
    svc = AudienceSelectionService()
    segments = (_seg("a", 0.4, 120, 0.8), _seg("b", 0.4, 120, 0.8))
    a = svc.select(segments)
    b = svc.select(segments)
    assert [s.segment.id for s in a] == [s.segment.id for s in b]


def test_score_is_zero_to_one():
    svc = AudienceSelectionService()
    selected = svc.select((_seg("x", 1.0, 100, 1.0),))
    assert 0.0 <= selected[0].score <= 1.0


def test_empty_input_returns_empty():
    assert AudienceSelectionService().select(()) == ()
