"""BigQuery audience-data adapter (AudienceDataPort) — GCP managed stack.

The primary D2 audience backend: **BigQuery** over the marketing data warehouse. The
adapter queries the segments table for candidate audience segments matching the objective,
market and vertical, and the benchmarks table for the per-channel cost / performance
assumptions the deterministic allocation engine consumes. It only *reads* the warehouse and
maps rows onto the domain :class:`AudienceSegment` and :class:`ChannelBenchmark` types
(each carrying a :class:`Citation` back to its source table); it never selects the audience
or allocates the budget itself.

The residency region is resolved from the requested market and **validated** against the
per-market allow-list (JP -> ``asia-northeast1``, AU -> ``australia-southeast1``, SG ->
``asia-southeast1``), so a query can never cross the configured residency boundary; the
BigQuery job ``location`` is pinned to the validated region.

All Google Cloud SDK imports are LAZY (inside methods) so the on-prem / local / test profile
imports this module with no ``google-cloud-bigquery`` installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...config import Settings
from ...domain.models import (
    AudienceSegment,
    Channel,
    ChannelBenchmark,
    Citation,
    Market,
    SourceType,
    Vertical,
)
from ._region import resolve_region

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.cloud import bigquery


class BigQueryAudienceDataAdapter:
    """Read audience segments and channel benchmarks from BigQuery."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bq = settings.bigquery
        self._client: Any | None = None

    # ------------------------------------------------------------------ #
    # Lazy, region-validated client construction
    # ------------------------------------------------------------------ #
    def _get_client(self, market: Market | None = None) -> bigquery.Client:
        region = resolve_region(self._settings, market)
        if self._client is None:
            from google.cloud import bigquery  # noqa: PLC0415 — lazy: gcp profile only

            self._client = bigquery.Client(project=self._settings.project_id, location=region)
        return self._client

    # ------------------------------------------------------------------ #
    # AudienceDataPort
    # ------------------------------------------------------------------ #
    def segments(
        self, objective: str, market: Market, vertical: Vertical
    ) -> tuple[AudienceSegment, ...]:
        """Query candidate audience segments for the objective, market and vertical."""
        from google.cloud import bigquery  # noqa: PLC0415 — lazy

        client = self._get_client(market)
        table = f"`{self._settings.project_id}.{self._bq.dataset}.{self._bq.segments_table}`"
        sql = (
            f"SELECT id, name, size, reachable_size, propensity, expected_value, "
            f"consent_rate, tags FROM {table} "
            "WHERE market = @market AND vertical = @vertical "
            "ORDER BY propensity DESC"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("market", "STRING", market.value),
                bigquery.ScalarQueryParameter("vertical", "STRING", vertical.value),
            ]
        )
        rows = client.query(
            sql, job_config=job_config, location=resolve_region(self._settings, market)
        )
        return tuple(self._to_segment(row, market, vertical) for row in rows)

    def channel_benchmarks(
        self, market: Market, vertical: Vertical
    ) -> tuple[ChannelBenchmark, ...]:
        """Query the per-channel cost / performance benchmarks for the allocation engine."""
        from google.cloud import bigquery  # noqa: PLC0415 — lazy

        client = self._get_client(market)
        table = f"`{self._settings.project_id}.{self._bq.dataset}.{self._bq.benchmarks_table}`"
        sql = (
            "SELECT channel, cpm, ctr, conversion_rate, max_reach, min_spend "
            f"FROM {table} WHERE market = @market AND vertical = @vertical"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("market", "STRING", market.value),
                bigquery.ScalarQueryParameter("vertical", "STRING", vertical.value),
            ]
        )
        rows = client.query(
            sql, job_config=job_config, location=resolve_region(self._settings, market)
        )
        return tuple(self._to_benchmark(row, market, vertical) for row in rows)

    # ------------------------------------------------------------------ #
    # Row mapping
    # ------------------------------------------------------------------ #
    def _to_segment(self, row: Any, market: Market, vertical: Vertical) -> AudienceSegment:
        sid = str(row["id"])
        tags = tuple(str(t) for t in (row.get("tags") or ()))
        return AudienceSegment(
            id=sid,
            name=str(row["name"]),
            market=market,
            vertical=vertical,
            size=int(row["size"]),
            reachable_size=int(row["reachable_size"]),
            propensity=float(row["propensity"]),
            expected_value=float(row["expected_value"]),
            consent_rate=float(row.get("consent_rate", 1.0) or 1.0),
            tags=tags,
            citations=(
                Citation(
                    source_id=sid,
                    source_type=SourceType.AUDIENCE_DATA,
                    title=f"BigQuery {self._bq.segments_table}: {row['name']}",
                    url=(
                        f"bq://{self._settings.project_id}.{self._bq.dataset}."
                        f"{self._bq.segments_table}"
                    ),
                    page=1,
                ),
            ),
        )

    def _to_benchmark(self, row: Any, market: Market, vertical: Vertical) -> ChannelBenchmark:
        channel = self._coerce_channel(row["channel"])
        sid = f"{market.value.lower()}-{vertical.value}-{channel.value}-bm"
        return ChannelBenchmark(
            channel=channel,
            market=market,
            vertical=vertical,
            cpm=float(row["cpm"]),
            ctr=float(row["ctr"]),
            conversion_rate=float(row["conversion_rate"]),
            max_reach=int(row["max_reach"]),
            min_spend=float(row.get("min_spend", 0.0) or 0.0),
            citations=(
                Citation(
                    source_id=sid,
                    source_type=SourceType.BENCHMARK,
                    title=f"BigQuery {self._bq.benchmarks_table}: {channel.value}",
                    url=(
                        f"bq://{self._settings.project_id}.{self._bq.dataset}."
                        f"{self._bq.benchmarks_table}"
                    ),
                    page=1,
                ),
            ),
        )

    @staticmethod
    def _coerce_channel(raw: Any) -> Channel:
        try:
            return Channel(str(raw))
        except ValueError:
            return Channel.OTHER
