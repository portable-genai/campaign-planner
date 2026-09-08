"""Local audience-data adapter (AudienceDataPort) : the laptop's DuckDB audience warehouse.

The ``local`` profile's stand-in for **BigQuery**: a DuckDB file holding the same two tables
the managed dataset holds, in the same column order, self-seeded from the shipped book under
``campaign_planner/data/demo_book/``. DuckDB is an embedded engine in a wheel, so this needs
no service and no credentials, and the offline gate stays offline while the store it
exercises is still SQL.

Holding the same shape as the managed store is the point, and here it was doing more work
than usual: the managed dataset this mirrors did not exist. Nothing in Terraform created
``mkt_campaign_audience`` or either of its tables, though the API was enabled, the roles were
granted and the CMEK binding was in place, all pointing at something nothing provisioned. The
schema this store declares and the schema Terraform now declares are held against each other
by a contract test, so the two cannot drift apart again while both look fine.

Segments are scoped by market and vertical, so a banking request in JP and a retail request
in SG each get their own fictional audience with no hard-coded branch in the engines.
"""

from __future__ import annotations

from pathlib import Path

from hex_service_kit.demobook import DuckDbStore

from ... import demo_book
from ...config import Settings
from ...domain.models import AudienceSegment, ChannelBenchmark, Market, Vertical

#: Default on-disk location for the laptop warehouse (settings.local.book_path overrides).
_DEFAULT_BOOK_PATH = Path.home() / ".campaign_planner" / "book.duckdb"

_SOURCE = "DuckDB audience warehouse (local)"


class LocalAudienceDataAdapter:
    """Serve audience segments and channel benchmarks from the laptop's DuckDB book."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        path = getattr(getattr(settings, "local", None), "book_path", "") or str(_DEFAULT_BOOK_PATH)
        self._store = DuckDbStore(demo_book.BOOK, path)
        self._conn = self._store.connection

    def close(self) -> None:
        """Close the connection (the CLI and tests reopen the same file)."""
        self._store.close()

    def segments(
        self, objective: str, market: Market, vertical: Vertical
    ) -> tuple[AudienceSegment, ...]:
        """Candidate segments for this market and vertical, most responsive first.

        The objective is not a filter here, exactly as in the managed adapter: the selection
        engine ranks the candidates against it deterministically, and narrowing them by a
        free-text match first would move that decision into a store nobody can audit.
        """
        columns = demo_book.AUDIENCE_SEGMENTS.columns
        rows = self._conn.execute(
            f"SELECT {', '.join(columns)} FROM audience_segments "
            "WHERE market = ? AND vertical = ? ORDER BY propensity DESC",
            [market.value, vertical.value],
        ).fetchall()
        return tuple(
            demo_book.to_segment(dict(zip(columns, row, strict=True)), _SOURCE) for row in rows
        )

    def channel_benchmarks(
        self, market: Market, vertical: Vertical
    ) -> tuple[ChannelBenchmark, ...]:
        columns = demo_book.CHANNEL_BENCHMARKS.columns
        rows = self._conn.execute(
            f"SELECT {', '.join(columns)} FROM channel_benchmarks "
            "WHERE market = ? AND vertical = ? ORDER BY channel",
            [market.value, vertical.value],
        ).fetchall()
        return tuple(demo_book.to_benchmark(dict(zip(columns, row, strict=True))) for row in rows)
