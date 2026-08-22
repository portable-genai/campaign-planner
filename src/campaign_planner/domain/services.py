"""Domain services aggregator — one import surface for the wiring layers.

The API, CLI and agent layers import services from here so that adding or renaming a
service is a single-file change at the boundary. The orchestrator (:class:`CampaignPlanService`)
composes the four deterministic engines and the ports.
"""

from __future__ import annotations

from .allocation_service import BudgetAllocationService
from .audience_service import AudienceSelectionService
from .pacing_service import PacingService
from .plan_service import CampaignPlanService
from .reach_service import ReachFrequencyService

__all__ = [
    "CampaignPlanService",
    "AudienceSelectionService",
    "BudgetAllocationService",
    "ReachFrequencyService",
    "PacingService",
]
