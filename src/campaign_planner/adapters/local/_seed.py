"""Built-in, OBVIOUSLY-FICTIONAL synthetic seed for the ``local`` profile.

This is the offline data warehouse stand-in that makes a local run grounded out of the box:
candidate audience segments and per-channel cost / performance benchmarks, spanning BOTH
verticals (banking AND online retail) across ALL THREE markets (JP, AU, SG). Every segment
and benchmark is invented (suffixed FICTIONAL) and every citation points at ``example.test``;
nothing here is real data.

The data is keyed by (market, vertical) so the local AudienceDataPort serves vertical- and
market-specific evidence, proving D2 is generic and APAC without any hard-coded branch in
the engines.
"""

from __future__ import annotations

from ...domain.models import (
    AudienceSegment,
    Channel,
    ChannelBenchmark,
    Citation,
    Market,
    SourceType,
    Vertical,
)

_Key = tuple[Market, Vertical]


def _seg_cit(sid: str, title: str) -> Citation:
    return Citation(
        source_id=sid,
        source_type=SourceType.AUDIENCE_DATA,
        title=title,
        url=f"https://example.test/audience/{sid}",
        page=1,
        snippet=f"{title} (FICTIONAL synthetic audience-data row).",
        score=0.9,
    )


def _bm_cit(sid: str, title: str) -> Citation:
    return Citation(
        source_id=sid,
        source_type=SourceType.BENCHMARK,
        title=title,
        url=f"https://example.test/benchmark/{sid}",
        page=1,
        snippet=f"{title} (FICTIONAL synthetic channel benchmark).",
        score=0.9,
    )


# --------------------------------------------------------------------------- #
# Audience segments, per (market, vertical)
# --------------------------------------------------------------------------- #
AUDIENCE_SEGMENTS: dict[_Key, tuple[AudienceSegment, ...]] = {
    (Market.SG, Vertical.BANKING): (
        AudienceSegment(
            id="sg-bank-seg-savers",
            name="SG affluent savers (FICTIONAL)",
            market=Market.SG,
            vertical=Vertical.BANKING,
            size=420_000,
            reachable_size=300_000,
            propensity=0.34,
            expected_value=180.0,
            consent_rate=0.82,
            tags=("savings", "affluent"),
            citations=(_seg_cit("sg-bank-seg-savers", "SG affluent savers"),),
        ),
        AudienceSegment(
            id="sg-bank-seg-young",
            name="SG under-30 first-account (FICTIONAL)",
            market=Market.SG,
            vertical=Vertical.BANKING,
            size=260_000,
            reachable_size=210_000,
            propensity=0.28,
            expected_value=90.0,
            consent_rate=0.74,
            tags=("youth", "acquisition"),
            citations=(_seg_cit("sg-bank-seg-young", "SG under-30 first-account"),),
        ),
    ),
    (Market.JP, Vertical.BANKING): (
        AudienceSegment(
            id="jp-bank-seg-fx",
            name="JP multi-currency travellers (FICTIONAL)",
            market=Market.JP,
            vertical=Vertical.BANKING,
            size=510_000,
            reachable_size=360_000,
            propensity=0.31,
            expected_value=210.0,
            consent_rate=0.79,
            tags=("fx", "travel"),
            citations=(_seg_cit("jp-bank-seg-fx", "JP multi-currency travellers"),),
        ),
        AudienceSegment(
            id="jp-bank-seg-salary",
            name="JP salaried direct-deposit (FICTIONAL)",
            market=Market.JP,
            vertical=Vertical.BANKING,
            size=880_000,
            reachable_size=600_000,
            propensity=0.22,
            expected_value=130.0,
            consent_rate=0.68,
            tags=("salary", "primary-account"),
            citations=(_seg_cit("jp-bank-seg-salary", "JP salaried direct-deposit"),),
        ),
    ),
    (Market.AU, Vertical.BANKING): (
        AudienceSegment(
            id="au-bank-seg-refi",
            name="AU home-loan refinancers (FICTIONAL)",
            market=Market.AU,
            vertical=Vertical.BANKING,
            size=190_000,
            reachable_size=150_000,
            propensity=0.37,
            expected_value=640.0,
            consent_rate=0.85,
            tags=("home-loan", "refinance"),
            citations=(_seg_cit("au-bank-seg-refi", "AU home-loan refinancers"),),
        ),
        AudienceSegment(
            id="au-bank-seg-savers",
            name="AU high-interest savers (FICTIONAL)",
            market=Market.AU,
            vertical=Vertical.BANKING,
            size=330_000,
            reachable_size=240_000,
            propensity=0.26,
            expected_value=150.0,
            consent_rate=0.8,
            tags=("savings",),
            citations=(_seg_cit("au-bank-seg-savers", "AU high-interest savers"),),
        ),
    ),
    (Market.SG, Vertical.ONLINE_RETAIL): (
        AudienceSegment(
            id="sg-retail-seg-cart",
            name="SG cart-abandoners 30d (FICTIONAL)",
            market=Market.SG,
            vertical=Vertical.ONLINE_RETAIL,
            size=150_000,
            reachable_size=130_000,
            propensity=0.41,
            expected_value=68.0,
            consent_rate=0.9,
            tags=("retargeting", "cart"),
            citations=(_seg_cit("sg-retail-seg-cart", "SG cart-abandoners 30d"),),
        ),
        AudienceSegment(
            id="sg-retail-seg-vip",
            name="SG repeat VIP shoppers (FICTIONAL)",
            market=Market.SG,
            vertical=Vertical.ONLINE_RETAIL,
            size=80_000,
            reachable_size=72_000,
            propensity=0.33,
            expected_value=120.0,
            consent_rate=0.94,
            tags=("loyalty", "vip"),
            citations=(_seg_cit("sg-retail-seg-vip", "SG repeat VIP shoppers"),),
        ),
    ),
    (Market.JP, Vertical.ONLINE_RETAIL): (
        AudienceSegment(
            id="jp-retail-seg-loyalty",
            name="JP points-loyalty members (FICTIONAL)",
            market=Market.JP,
            vertical=Vertical.ONLINE_RETAIL,
            size=620_000,
            reachable_size=540_000,
            propensity=0.3,
            expected_value=54.0,
            consent_rate=0.88,
            tags=("loyalty", "points"),
            citations=(_seg_cit("jp-retail-seg-loyalty", "JP points-loyalty members"),),
        ),
        AudienceSegment(
            id="jp-retail-seg-new",
            name="JP first-purchase prospects (FICTIONAL)",
            market=Market.JP,
            vertical=Vertical.ONLINE_RETAIL,
            size=400_000,
            reachable_size=320_000,
            propensity=0.19,
            expected_value=42.0,
            consent_rate=0.71,
            tags=("acquisition",),
            citations=(_seg_cit("jp-retail-seg-new", "JP first-purchase prospects"),),
        ),
    ),
    (Market.AU, Vertical.ONLINE_RETAIL): (
        AudienceSegment(
            id="au-retail-seg-bnpl",
            name="AU BNPL-friendly shoppers (FICTIONAL)",
            market=Market.AU,
            vertical=Vertical.ONLINE_RETAIL,
            size=240_000,
            reachable_size=200_000,
            propensity=0.36,
            expected_value=88.0,
            consent_rate=0.86,
            tags=("bnpl", "checkout"),
            citations=(_seg_cit("au-retail-seg-bnpl", "AU BNPL-friendly shoppers"),),
        ),
        AudienceSegment(
            id="au-retail-seg-seasonal",
            name="AU seasonal-sale browsers (FICTIONAL)",
            market=Market.AU,
            vertical=Vertical.ONLINE_RETAIL,
            size=350_000,
            reachable_size=280_000,
            propensity=0.24,
            expected_value=60.0,
            consent_rate=0.82,
            tags=("seasonal", "sale"),
            citations=(_seg_cit("au-retail-seg-seasonal", "AU seasonal-sale browsers"),),
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Channel benchmarks, per (market, vertical)
# --------------------------------------------------------------------------- #
def _channels_for(
    key: _Key, rows: tuple[tuple[Channel, float, float, float, int, float], ...]
) -> tuple[ChannelBenchmark, ...]:
    market, vertical = key
    out: list[ChannelBenchmark] = []
    for channel, cpm, ctr, conv, max_reach, min_spend in rows:
        sid = f"{market.value.lower()}-{vertical.value}-{channel.value}-bm"
        out.append(
            ChannelBenchmark(
                channel=channel,
                market=market,
                vertical=vertical,
                cpm=cpm,
                ctr=ctr,
                conversion_rate=conv,
                max_reach=max_reach,
                min_spend=min_spend,
                citations=(
                    _bm_cit(sid, f"{channel.value} benchmark {market.value}/{vertical.value}"),
                ),
            )
        )
    return tuple(out)


# (channel, cpm, ctr, conversion_rate, max_reach, min_spend)
_BANKING_CHANNELS = (
    (Channel.SEARCH, 9.0, 0.045, 0.06, 120_000, 0.0),
    (Channel.SOCIAL, 6.0, 0.012, 0.02, 400_000, 0.0),
    (Channel.DISPLAY, 3.5, 0.004, 0.008, 600_000, 0.0),
    (Channel.EMAIL, 1.2, 0.08, 0.03, 200_000, 0.0),
    (Channel.PARTNER, 7.5, 0.02, 0.04, 90_000, 5_000.0),
)
_RETAIL_CHANNELS = (
    (Channel.SEARCH, 7.0, 0.05, 0.05, 150_000, 0.0),
    (Channel.SOCIAL, 5.0, 0.018, 0.03, 500_000, 0.0),
    (Channel.DISPLAY, 3.0, 0.005, 0.01, 700_000, 0.0),
    (Channel.VIDEO, 8.0, 0.01, 0.015, 450_000, 0.0),
    (Channel.EMAIL, 1.0, 0.1, 0.04, 250_000, 0.0),
)

CHANNEL_BENCHMARKS: dict[_Key, tuple[ChannelBenchmark, ...]] = {
    (Market.SG, Vertical.BANKING): _channels_for((Market.SG, Vertical.BANKING), _BANKING_CHANNELS),
    (Market.JP, Vertical.BANKING): _channels_for((Market.JP, Vertical.BANKING), _BANKING_CHANNELS),
    (Market.AU, Vertical.BANKING): _channels_for((Market.AU, Vertical.BANKING), _BANKING_CHANNELS),
    (Market.SG, Vertical.ONLINE_RETAIL): _channels_for(
        (Market.SG, Vertical.ONLINE_RETAIL), _RETAIL_CHANNELS
    ),
    (Market.JP, Vertical.ONLINE_RETAIL): _channels_for(
        (Market.JP, Vertical.ONLINE_RETAIL), _RETAIL_CHANNELS
    ),
    (Market.AU, Vertical.ONLINE_RETAIL): _channels_for(
        (Market.AU, Vertical.ONLINE_RETAIL), _RETAIL_CHANNELS
    ),
}
