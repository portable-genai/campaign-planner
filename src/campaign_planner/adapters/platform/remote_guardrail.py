"""Remote-platform guardrail adapter (GuardrailPort) — thin client to the A1 gateway.

When D2 reuses the shared platform, prompt/response screening is the A1 Guardrail Gateway.
This adapter implements the port by POSTing to A1's screen endpoint; constructs cleanly with
no Google Cloud SDK. The HTTP body is wired in the platform phase.
"""

from __future__ import annotations

from ...domain.errors import CampaignPlanError
from ...domain.models import Direction, GuardrailVerdict
from ...envread import setting_or_default

_DEFAULT_URL = "http://localhost:8080"
_PHASE = "RemoteGuardrailAdapter screen() is wired in the platform phase."


class RemoteGuardrailError(CampaignPlanError):
    """Raised when the A1 guardrail service returns a non-2xx response."""


class RemoteGuardrailAdapter:
    """HTTP client for the shared A1 guardrail gateway."""

    def __init__(self, settings: object) -> None:
        self._settings = settings
        self._base_url = setting_or_default("GUARDRAIL_GATEWAY_URL", _DEFAULT_URL).rstrip("/")

    def screen(self, text: str, direction: Direction) -> GuardrailVerdict:
        raise NotImplementedError(_PHASE)
