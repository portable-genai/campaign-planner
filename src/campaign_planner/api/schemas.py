"""API request/response schemas (thin Pydantic models at the HTTP boundary)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..domain.models import AgentCard


class PlanRequestModel(BaseModel):
    objective: str = Field(..., description="The campaign objective.")
    market: str = Field("SG", description="Market: JP | AU | SG.")
    vertical: str = Field("banking", description="Vertical: banking | online_retail.")
    total_budget: float = Field(..., gt=0, description="Total budget in market currency.")
    start_date: date = Field(..., description="Flight start date (ISO).")
    end_date: date = Field(..., description="Flight end date (ISO).")
    flight_legs: int = Field(4, ge=1, description="Number of pacing legs.")
    pacing: str = Field("even", description="Pacing: even | front_loaded | back_loaded.")
    max_segments: int = Field(5, ge=1, description="Max audience segments to target.")
    channels: list[str] = Field(default_factory=list, description="Restrict to these channels.")
    effective_frequency: int = Field(3, ge=1, description="Effective-frequency threshold.")


class HealthModel(BaseModel):
    status: str = "ok"
    profile: str
    market: str
    vertical: str


class AgentSkillModel(BaseModel):
    id: str
    name: str
    description: str


class AgentCardModel(BaseModel):
    """A2A AgentCard served at ``/.well-known/agent-card.json`` (Hrz3 discovery shape)."""

    name: str
    description: str
    url: str
    version: str
    skills: list[AgentSkillModel] = Field(default_factory=list)
    provider: str

    @classmethod
    def from_domain(cls, card: AgentCard) -> AgentCardModel:
        return cls(
            name=card.name,
            description=card.description,
            url=card.url,
            version=card.version,
            skills=[
                AgentSkillModel(id=s.id, name=s.name, description=s.description)
                for s in card.skills
            ],
            provider=card.provider,
        )
