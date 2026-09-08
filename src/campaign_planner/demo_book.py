"""The shipped demo book: fictional audience segments and per-channel benchmarks.

The rows live as newline-delimited JSON under ``campaign_planner/data/demo_book/``, one file
per BigQuery table and in that table's column order, so one set of files feeds the DuckDB
store the ``local`` profile reads, the loader that fills the managed dataset, and the tests.
The reading, the overwrite guard and the tenant rule come from
:mod:`hex_service_kit.demobook`; what is here is about THIS system.

**The managed dataset did not exist.** ``config/settings.yaml`` has named
``mkt_campaign_audience`` and its two tables since the repository was written, the adapter
queries them, and no Terraform file created either the dataset or the tables. The API was
enabled, the IAM roles were granted and the CMEK binding was in place, all pointing at
something nothing provisioned, so the managed profile would have failed at the first request
on a deployment with a not-found rather than anything that explained itself.

Everything is fictional. See ``data/demo_book/README.md``.
"""

from __future__ import annotations

from typing import Any

from hex_service_kit.demobook import BookError, NdjsonBook, Table

from .domain.models import (
    AudienceSegment,
    Channel,
    ChannelBenchmark,
    Citation,
    Market,
    SourceType,
    Vertical,
)

SHIPPED_TENANT = "demo-bank"
CROSS_TENANT: dict[str, str] = {}

AUDIENCE_SEGMENTS = Table(
    name="audience_segments",
    columns=(
        "id",
        "name",
        "market",
        "vertical",
        "size",
        "reachable_size",
        "propensity",
        "expected_value",
        "consent_rate",
        "tags",
        "evidence_summary",
    ),
    types={
        "id": "TEXT NOT NULL",
        "name": "TEXT NOT NULL",
        "market": "TEXT NOT NULL",
        "vertical": "TEXT NOT NULL",
        "size": "BIGINT NOT NULL",
        "reachable_size": "BIGINT NOT NULL",
        "propensity": "DOUBLE NOT NULL",
        "expected_value": "DOUBLE NOT NULL",
        "consent_rate": "DOUBLE NOT NULL",
        "tags": "TEXT[]",
        "evidence_summary": "TEXT NOT NULL",
    },
    primary_key=("id",),
)

CHANNEL_BENCHMARKS = Table(
    name="channel_benchmarks",
    columns=(
        "channel",
        "market",
        "vertical",
        "cpm",
        "ctr",
        "conversion_rate",
        "max_reach",
        "min_spend",
    ),
    types={
        "channel": "TEXT NOT NULL",
        "market": "TEXT NOT NULL",
        "vertical": "TEXT NOT NULL",
        "cpm": "DOUBLE NOT NULL",
        "ctr": "DOUBLE NOT NULL",
        "conversion_rate": "DOUBLE NOT NULL",
        "max_reach": "BIGINT NOT NULL",
        "min_spend": "DOUBLE NOT NULL",
    },
    primary_key=("channel", "market", "vertical"),
)

TABLES = (AUDIENCE_SEGMENTS, CHANNEL_BENCHMARKS)

BOOK = NdjsonBook("campaign_planner.data.demo_book", TABLES)


def validate() -> None:
    """The book's own invariants, on top of the shape the kit checks.

    Every rule here is arithmetic the allocation engine depends on and a hand edit can break
    silently: a segment nobody can reach, a consent rate above one that would let a plan
    target more people than consented, a market with segments and no benchmarks to spend on,
    or a zero CPM that would make a channel look infinitely cheap and take the whole budget.
    """
    BOOK.validate()
    segments = BOOK.rows("audience_segments")
    benchmarks = BOOK.rows("channel_benchmarks")
    if not segments or not benchmarks:
        raise BookError("the book ships no segments or no benchmarks")

    for row in segments:
        where = row["id"]
        if int(row["reachable_size"]) > int(row["size"]):
            raise BookError(f"{where} is reachable beyond its own population")
        if not 0.0 <= float(row["consent_rate"]) <= 1.0:
            raise BookError(f"{where} has a consent rate outside 0..1")
        if not 0.0 <= float(row["propensity"]) <= 1.0:
            raise BookError(f"{where} has a propensity outside 0..1")
        if float(row["expected_value"]) <= 0:
            raise BookError(f"{where} has no expected value, so it can never be worth targeting")

    for row in benchmarks:
        where = f"{row['market']}/{row['vertical']}/{row['channel']}"
        if float(row["cpm"]) <= 0:
            raise BookError(f"{where} has a zero or negative CPM; it would look free to buy")
        for rate in ("ctr", "conversion_rate"):
            if not 0.0 <= float(row[rate]) <= 1.0:
                raise BookError(f"{where} has a {rate} outside 0..1")
        if int(row["max_reach"]) <= 0:
            raise BookError(f"{where} can reach nobody")

    segment_scopes = {(row["market"], row["vertical"]) for row in segments}
    benchmark_scopes = {(row["market"], row["vertical"]) for row in benchmarks}
    missing = sorted(segment_scopes - benchmark_scopes)
    if missing:
        raise BookError(f"markets with segments and no channel benchmarks: {missing}")


# --------------------------------------------------------------------------- #
# Row to domain
# --------------------------------------------------------------------------- #
def to_segment(row: dict[str, Any], source: str) -> AudienceSegment:
    return AudienceSegment(
        id=str(row["id"]),
        name=str(row["name"]),
        market=Market(str(row["market"])),
        vertical=Vertical(str(row["vertical"])),
        size=int(row["size"]),
        reachable_size=int(row["reachable_size"]),
        propensity=float(row["propensity"]),
        expected_value=float(row["expected_value"]),
        consent_rate=float(row.get("consent_rate", 1.0)),
        tags=tuple(str(tag) for tag in row.get("tags") or ()),
        citations=(
            Citation(
                source_id=str(row["id"]),
                source_type=SourceType.AUDIENCE_DATA,
                title=str(row["name"]),
                snippet=str(row.get("evidence_summary") or source),
            ),
        ),
    )


def to_benchmark(row: dict[str, Any]) -> ChannelBenchmark:
    return ChannelBenchmark(
        channel=Channel(str(row["channel"])),
        market=Market(str(row["market"])),
        vertical=Vertical(str(row["vertical"])),
        cpm=float(row["cpm"]),
        ctr=float(row["ctr"]),
        conversion_rate=float(row["conversion_rate"]),
        max_reach=int(row["max_reach"]),
        min_spend=float(row.get("min_spend", 0.0)),
    )
