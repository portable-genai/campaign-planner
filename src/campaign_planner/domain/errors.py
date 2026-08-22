"""Domain exceptions for the Campaign Planning system (D2).

Pure-Python exception hierarchy raised by the orchestration services. The domain layer
never imports Google Cloud, ADK, or any framework: these errors let callers (API, CLI,
the agent runtime adapter) react to domain-level failures without coupling to any vendor
SDK error type.
"""

from __future__ import annotations


class CampaignPlanError(Exception):
    """Base class for all domain-level errors raised by D2 services."""


class GuardrailBlockedError(CampaignPlanError):
    """Flagged / raised when the A1 guardrail blocks an input or output.

    A blocked unsafe request must never yield a partial plan: the orchestrator raises this
    rather than assembling a plan from screened-out content.
    """


class NoAudienceError(CampaignPlanError):
    """Raised when no consented, reachable audience segment exists for the request.

    A campaign plan must target a real, reachable, consented audience; an empty audience is
    a hard error so a plan is never built to spend against nobody.
    """


class NoChannelBenchmarkError(CampaignPlanError):
    """Raised when no channel benchmarks are available for the (market, vertical)."""


class InvalidBudgetError(CampaignPlanError):
    """Raised when the requested budget is non-positive or below the channel floors."""


class InvalidFlightError(CampaignPlanError):
    """Raised when the flight window or leg count is invalid (end before start, etc.)."""


class UnsupportedMarketError(CampaignPlanError):
    """Raised when a requested market has no configured residency region / profile."""


class UnsupportedVerticalError(CampaignPlanError):
    """Raised when a requested vertical has no configured seed / taxonomy."""
