"""Unit tests for config (vertical/market/region) and the local audience-data store."""

from __future__ import annotations

from campaign_planner.adapters.local.audience import LocalAudienceDataAdapter
from campaign_planner.config import Settings
from campaign_planner.domain.models import Market, Vertical


def test_config_resolves_active_vertical_and_market(local_settings: Settings):
    assert local_settings.active_vertical is Vertical(local_settings.vertical)
    assert local_settings.active_market is Market(local_settings.market)


def test_market_profiles_carry_residency_regions(local_settings: Settings):
    assert local_settings.market_profile(Market.JP).region == "asia-northeast1"
    assert local_settings.market_profile(Market.AU).region == "australia-southeast1"
    assert local_settings.market_profile(Market.SG).region == "asia-southeast1"


def test_jp_profile_is_bilingual(local_settings: Settings):
    assert local_settings.market_profile(Market.JP).locales == ("ja", "en")


def test_env_overrides_select_vertical_and_market(monkeypatch):
    monkeypatch.setenv("MKT_VERTICAL", "online_retail")
    monkeypatch.setenv("MKT_MARKET", "JP")
    settings = Settings.load("config/settings.yaml")
    assert settings.active_vertical is Vertical.ONLINE_RETAIL
    assert settings.active_market is Market.JP


def test_local_audience_returns_scoped_cited_segments(local_settings: Settings):
    adapter = LocalAudienceDataAdapter(local_settings)
    segments = adapter.segments("savings", Market.SG, Vertical.BANKING)
    assert segments, "local audience-data store returned nothing for the seeded data"
    for s in segments:
        assert s.market is Market.SG
        assert s.vertical is Vertical.BANKING
        assert s.citations
        assert s.consented_reachable <= s.reachable_size


def test_local_audience_scope_excludes_other_market(local_settings: Settings):
    adapter = LocalAudienceDataAdapter(local_settings)
    sg = adapter.segments("x", Market.SG, Vertical.BANKING)
    assert all(s.market is Market.SG for s in sg)


def test_local_benchmarks_cover_both_verticals(local_settings: Settings):
    adapter = LocalAudienceDataAdapter(local_settings)
    bank = adapter.channel_benchmarks(Market.SG, Vertical.BANKING)
    retail = adapter.channel_benchmarks(Market.SG, Vertical.ONLINE_RETAIL)
    assert bank and retail
    assert all(b.cost_per_conversion > 0 for b in bank)
