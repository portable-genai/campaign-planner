"""AudienceDataPort — audience segments and channel benchmarks.

Primary GCP adapter: **BigQuery** over the marketing data warehouse (audience / segment
tables and channel cost / performance benchmark tables). The port returns the candidate
audience segments for an objective and the per-channel benchmarks the deterministic
allocation engine consumes; it never selects the audience or allocates the budget itself.
The local adapter is a deterministic, seedable in-process store; the on-prem adapter is a
fail-fast migration placeholder.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import AudienceSegment, ChannelBenchmark, Market, Vertical


@runtime_checkable
class AudienceDataPort(Protocol):
    def segments(
        self, objective: str, market: Market, vertical: Vertical
    ) -> tuple[AudienceSegment, ...]:
        """Return candidate audience segments for the objective, market and vertical."""
        ...

    def channel_benchmarks(
        self, market: Market, vertical: Vertical
    ) -> tuple[ChannelBenchmark, ...]:
        """Return the per-channel cost / performance benchmarks for the allocation engine."""
        ...
