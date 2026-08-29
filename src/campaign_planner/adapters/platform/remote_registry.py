"""Remote-platform registry adapter (AgentRegistryPort) — thin client to the A3 registry.

When D2 reuses the shared platform, agent discovery is the A3 Agent Registry. This adapter
implements the port by calling A3; constructs cleanly with no Google Cloud SDK. The HTTP body
is wired in the platform phase.
"""

from __future__ import annotations

from ...domain.errors import CampaignPlanError
from ...domain.models import AgentCard
from ...envread import setting_or_default

_DEFAULT_URL = "http://localhost:8086"
_PHASE = "RemoteRegistryAdapter is wired in the platform phase."


class RemoteRegistryError(CampaignPlanError):
    """Raised when the A3 registry service returns a non-2xx response."""


class RemoteRegistryAdapter:
    """HTTP client for the shared A3 agent registry."""

    def __init__(self, settings: object) -> None:
        self._settings = settings
        self._base_url = setting_or_default("AGENT_REGISTRY_URL", _DEFAULT_URL).rstrip("/")

    def register(self, card: AgentCard) -> None:
        raise NotImplementedError(_PHASE)

    def get(self, name: str) -> AgentCard | None:
        raise NotImplementedError(_PHASE)

    def list(self) -> list[AgentCard]:
        raise NotImplementedError(_PHASE)
