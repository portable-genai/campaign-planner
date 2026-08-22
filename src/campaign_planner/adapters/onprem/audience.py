"""On-prem placeholder for ``AudienceDataPort`` — the sovereign migration target.

A reversibility (no-lock-in) placeholder: in the managed profile this port binds to the
BigQuery audience-data adapter; switching ``profile`` to ``onprem`` rebinds it here. The
adapter constructs cleanly with **no external dependencies** and structurally satisfies the
same Protocol, so the contract tests prove interface parity. Porting D2 on-premise is only
a matter of filling these bodies in; the domain orchestration does not change.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AudienceSegment, ChannelBenchmark, Market, Vertical

_MESSAGE = (
    "On-prem AudienceDataPort adapter is a migration placeholder; implement against your "
    "on-premise audience warehouse. Core domain logic is unchanged."
)


class OnPremAudienceDataAdapter:
    """Placeholder audience-data adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def segments(
        self, objective: str, market: Market, vertical: Vertical
    ) -> tuple[AudienceSegment, ...]:
        raise NotImplementedError(_MESSAGE)

    def channel_benchmarks(
        self, market: Market, vertical: Vertical
    ) -> tuple[ChannelBenchmark, ...]:
        raise NotImplementedError(_MESSAGE)
