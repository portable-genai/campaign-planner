"""Remote-platform audit adapter (AuditSinkPort) — thin client to the shared A5 sink.

When D2 reuses the shared platform, audit events go to the A5 observability / audit sink.
This adapter implements the port by POSTing to A5; constructs cleanly with no Google Cloud
SDK. The HTTP body is wired in the platform phase.
"""

from __future__ import annotations

from ...domain.errors import CampaignPlanError
from ...domain.models import AuditEvent
from ...envread import setting_or_default

_DEFAULT_URL = "http://localhost:8085"
_PHASE = "RemoteAuditAdapter record() is wired in the platform phase."


class RemoteAuditError(CampaignPlanError):
    """Raised when the A5 audit service returns a non-2xx response."""


class RemoteAuditAdapter:
    """HTTP client for the shared A5 audit sink."""

    def __init__(self, settings: object) -> None:
        self._settings = settings
        self._base_url = setting_or_default("HRZ_AUDIT_URL", _DEFAULT_URL).rstrip("/")

    def record(self, event: AuditEvent) -> None:
        raise NotImplementedError(_PHASE)
