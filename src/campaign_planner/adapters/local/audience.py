"""Local audience-data adapter (AudienceDataPort) — deterministic seeded store.

The ``local`` profile's stand-in for **BigQuery**: a deterministic, seedable in-process
store over the bundled fictional data (``_seed.py``), with no model and no network. It
returns candidate audience segments for the requested (objective, market, vertical) and the
per-channel benchmarks the deterministic allocation engine compares. SDK-free and
unconditional (there is no offline BigQuery for this seed), and reproducible so the offline
CLI and the unit tests agree.

Segments are keyed by (market, vertical) so a banking request in JP and a retail request in
SG each get their own fictional audience, proving D2 is generic and APAC with no hard-coded
branch in the engines.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AudienceSegment, ChannelBenchmark, Market, Vertical
from ._seed import AUDIENCE_SEGMENTS, CHANNEL_BENCHMARKS


class LocalAudienceDataAdapter:
    """Deterministic audience-data store over the seeded fictional warehouse."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def segments(
        self, objective: str, market: Market, vertical: Vertical
    ) -> tuple[AudienceSegment, ...]:
        return AUDIENCE_SEGMENTS.get((market, vertical), ())

    def channel_benchmarks(
        self, market: Market, vertical: Vertical
    ) -> tuple[ChannelBenchmark, ...]:
        return CHANNEL_BENCHMARKS.get((market, vertical), ())
