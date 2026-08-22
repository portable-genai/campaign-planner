"""Service factories — build domain services from the DI container.

One place that wires the ports resolved by :class:`campaign_planner.config.Container` into
the domain orchestrator, so the CLI, API and agent layers share identical wiring.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import Container, build_container
from ..domain.allocation_service import BudgetAllocationService
from ..domain.audience_service import AudienceSelectionService
from ..domain.pacing_service import PacingService
from ..domain.reach_service import ReachFrequencyService
from ..domain.services import CampaignPlanService


@lru_cache(maxsize=1)
def get_container() -> Container:
    return build_container()


def make_plan_service(container: Container | None = None) -> CampaignPlanService:
    container = container or get_container()
    policy = container.settings.policy
    return CampaignPlanService(
        audience=container.audience,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
        selection=AudienceSelectionService(
            propensity_weight=policy.audience_propensity_weight,
            value_weight=policy.audience_value_weight,
            min_consent=policy.audience_min_consent,
            min_reachable=policy.audience_min_reachable,
        ),
        allocation=BudgetAllocationService(
            saturation_frequency=policy.allocation_saturation_frequency,
            epsilon=policy.allocation_epsilon,
        ),
        reach=ReachFrequencyService(effective_reach_factor=policy.reach_effective_factor),
        pacing=PacingService(
            ramp_low=policy.pacing_ramp_low,
            ramp_high=policy.pacing_ramp_high,
        ),
        review_router=container.review_router,
    )


def make_audience_selection_service(
    container: Container | None = None,
) -> AudienceSelectionService:
    """Build the standalone agent-tool selector from the same adopter policy."""
    container = container or get_container()
    policy = container.settings.policy
    return AudienceSelectionService(
        propensity_weight=policy.audience_propensity_weight,
        value_weight=policy.audience_value_weight,
        min_consent=policy.audience_min_consent,
        min_reachable=policy.audience_min_reachable,
    )
