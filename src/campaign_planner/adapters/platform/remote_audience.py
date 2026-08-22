"""Remote-platform audience adapter (AudienceDataPort) — thin client to the shared plane.

When D2 reuses the shared platform, audience segments and channel benchmarks come from the
shared marketing data plane. This adapter implements the port by calling that service;
constructs cleanly with no Google Cloud SDK. The HTTP body is wired in the platform phase.
"""

from __future__ import annotations

from ...domain.errors import CampaignPlanError
from ...domain.models import AudienceSegment, ChannelBenchmark, Market, Vertical
from ...envread import setting_or_default

_DEFAULT_URL = "http://localhost:8083"
_PHASE = "RemoteAudienceDataAdapter is wired in the platform phase."


class RemoteAudienceDataError(CampaignPlanError):
    """Raised when the shared audience-data service returns a non-2xx response."""


class RemoteAudienceDataAdapter:
    """HTTP client for the shared marketing audience-data plane."""

    def __init__(self, settings: object) -> None:
        self._settings = settings
        self._base_url = setting_or_default("MKT_AUDIENCE_URL", _DEFAULT_URL).rstrip("/")

    def segments(
        self, objective: str, market: Market, vertical: Vertical
    ) -> tuple[AudienceSegment, ...]:
        raise NotImplementedError(_PHASE)

    def channel_benchmarks(
        self, market: Market, vertical: Vertical
    ) -> tuple[ChannelBenchmark, ...]:
        raise NotImplementedError(_PHASE)
