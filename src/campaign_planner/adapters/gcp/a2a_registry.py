"""A2A registry adapter (AgentRegistryPort) — agent discovery and governance for D2 (A3).

Backs the domain ``AgentRegistryPort`` with an in-process, **A2A v1.0**-style registry of
:class:`AgentCard` objects. In a standalone deployment D2 registers its own card here and
can serve it at the well-known A2A discovery path; inside the full platform the ``platform``
profile swaps this for a thin client to the shared agent registry.

A2A discovery contract: an agent publishes its capabilities as an **AgentCard** served at
``/.well-known/agent-card.json``; peers fetch that card to learn the agent's skills,
endpoint URL and version before initiating an A2A task. ``agent_card_dict`` produces that
JSON body. No external call is required: this adapter is pure, in-memory governance, so it
needs no Google import and constructs cleanly under any profile.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AgentCard, AgentSkill

# The A2A well-known discovery path for an agent's card.
AGENT_CARD_PATH = "/.well-known/agent-card.json"

# D2's own skills, surfaced on its AgentCard so peers / the registry can discover the
# governed campaign-planning capabilities the system offers (generic across verticals).
_D2_SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="campaign_plan",
        name="Cited campaign plan",
        description=(
            "Build a cited campaign plan for an objective: audience selection, channel-mix "
            "budget allocation, reach / frequency and a pacing calendar, for any of "
            "banking / online retail across JP/AU/SG."
        ),
    ),
    AgentSkill(
        id="budget_allocation",
        name="Budget allocation",
        description=(
            "Allocate a total budget across channels by deterministic cost-per-conversion, "
            "with provenance on every figure. Output requires human review."
        ),
    ),
)


class A2ARegistryAdapter:
    """In-process A2A AgentCard registry: register / get / list, plus card export."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cards: dict[str, AgentCard] = {}
        # Seed the registry with D2's own card so a standalone deployment is discoverable.
        self.register(self._self_card())

    # ------------------------------------------------------------------ #
    # AgentRegistryPort
    # ------------------------------------------------------------------ #
    def register(self, card: AgentCard) -> None:
        self._cards[card.name] = card

    def get(self, name: str) -> AgentCard | None:
        return self._cards.get(name)

    def list(self) -> list[AgentCard]:
        return list(self._cards.values())

    # ------------------------------------------------------------------ #
    # A2A discovery helper
    # ------------------------------------------------------------------ #
    def agent_card_dict(self, name: str | None = None) -> dict:
        """Return the ``/.well-known/agent-card.json`` body for ``name`` (default: D2's)."""
        card = self.get(name) if name else self._cards.get(self._self_name())
        if card is None:
            raise KeyError(f"No AgentCard registered for '{name}'.")
        return {
            "name": card.name,
            "description": card.description,
            "url": card.url,
            "version": card.version,
            "provider": card.provider,
            "skills": [
                {"id": s.id, "name": s.name, "description": s.description} for s in card.skills
            ],
        }

    # ------------------------------------------------------------------ #
    # D2's own card
    # ------------------------------------------------------------------ #
    def _self_name(self) -> str:
        return self._settings.agent_engine.display_name or "campaign-planner"

    def _self_card(self) -> AgentCard:
        return AgentCard(
            name=self._self_name(),
            description=(
                "D2 Campaign Planning and Budget Allocation — deterministic audience "
                "selection, channel-mix budget allocation, reach / frequency and pacing, "
                "generic across banking and online retail and the JP/AU/SG markets, with "
                "cited figures and maker-checker review."
            ),
            url=f"https://campaign-planner.{self._settings.region}.example/a2a",
            version="1.0.0",
            skills=_D2_SKILLS,
            provider="campaign-planner",
        )
