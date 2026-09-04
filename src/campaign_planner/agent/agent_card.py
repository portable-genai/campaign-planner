"""A2A AgentCard for the D2 Campaign Planner agent (A3 Registry & Governance).

This builds the agent's discovery card (the same minimal A2A shape the ``agent-registry``
service stores and serves, SPEC §6). It is published at ``/.well-known/agent-card.json``;
:func:`agent_card_document` returns the JSON-safe body the API layer serves there, and the
``platform`` registry adapter registers the same card in agent-registry (rule R4).

The card advertises the two skills D2 produces (build_campaign_plan, select_audience),
mirroring the ADK FunctionTools so a peer agent or the registry sees one consistent capability
surface.

This module is pure (domain models only) and imports without ADK or any Google Cloud SDK
installed (SPEC §4).
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..domain.models import AgentCard, AgentSkill

SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="build_campaign_plan",
        name="Campaign plan",
        description=(
            "Turn an objective and budget into a full cited campaign plan for a market "
            "(JP / AU / SG) and vertical (banking / online retail): audience selection, "
            "deterministic channel-mix and budget allocation, reach and frequency, pacing "
            "legs, plus a narrated brief and calendar. Always flagged for human review (P-06)."
        ),
    ),
    AgentSkill(
        id="select_audience",
        name="Audience selection",
        description=(
            "Select and rank the target audience segments for an objective (propensity- and "
            "value-ranked, consent- and reachability-filtered). An input to a plan, not a "
            "consequential output."
        ),
    ),
)

_DESCRIPTION = (
    "Campaign-planning agent for a bank or online retailer. Turns an objective and budget "
    "into a cited campaign plan (audience segmentation, deterministic channel-mix and budget "
    "allocation, reach and frequency, pacing calendar and creative brief), generic across "
    "banking and online retail and the JP / AU / SG markets. Built ports-and-adapters on the "
    "Gemini Enterprise Agent Platform. The model only narrates the deterministically-computed "
    "allocation; every consequential figure carries a citation."
)


def build_agent_card(settings: Settings) -> AgentCard:
    """Construct the A2A :class:`AgentCard` for this agent."""
    return AgentCard(
        name="campaign-planner",
        description=_DESCRIPTION,
        url=_resolve_url(settings),
        version="0.1.0",
        skills=SKILLS,
        provider="campaign-planner",
    )


def agent_card_document(settings: Settings) -> dict[str, Any]:
    """Return the JSON-safe body to serve at ``/.well-known/agent-card.json``."""
    from ..domain.serialization import to_jsonable

    return to_jsonable(build_agent_card(settings))


def _resolve_url(settings: Settings) -> str:
    """Best-effort public URL for the card, region-pinned to the active market."""
    resource = settings.agent_engine.resource_name
    if resource:
        return f"https://aiplatform.googleapis.com/v1/{resource}"
    return "https://campaign-planner.mkt.internal/a2a"
