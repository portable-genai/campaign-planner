"""CampaignPlanService — the campaign-planning orchestrator.

Owns the full plan pipeline and calls only ports plus the deterministic engines. The
deterministic engines (audience selection, budget allocation, reach / frequency, pacing)
decide everything consequential; the LLM only drafts the creative brief and narrates the
plan summary. Every consequential output is maker-checker gated: the plan and its budget
allocation always require human review before any spend is committed.

Pipeline (each step wrapped in ``tracer.span``; audited at the end):

    tracer.span("plan.build"):
      guardrail.screen(INPUT)                       [blocked -> audit BLOCKED + raise]
      -> audience.segments(objective, market, vertical)   (BigQuery audience-data)
      -> select segments (propensity x value x consent)   [empty -> NoAudienceError]
      -> audience.channel_benchmarks(market, vertical)    (BigQuery benchmarks)
      -> allocate budget across channels (optimiser)      [invalid -> InvalidBudgetError]
      -> estimate reach / frequency (over the addressable audience)
      -> build the flight schedule (pacing calendar)
      -> llm.generate(creative brief + summary)   (drafting only, over computed plan)
      -> assemble Plan (requires_human_review=True)
      -> guardrail.screen(OUTPUT)                   [blocked -> audit BLOCKED + raise]
      -> audit.record

Defensive throughout: tracing that degrades is tolerated, but a blocked input and a plan
with no consented audience or no benchmarks are hard errors so a plan is never built to
spend against nobody or with no cost basis.

Pure domain code: no Google Cloud / ADK / FastAPI imports.
"""

from __future__ import annotations

import contextlib
import json
from contextlib import nullcontext
from typing import Any

from .allocation_service import BudgetAllocationService
from .audience_service import AudienceSelectionService
from .errors import GuardrailBlockedError, NoAudienceError
from .models import (
    AuditEvent,
    Citation,
    Decision,
    Direction,
    GuardrailVerdict,
    LlmMessage,
    LlmRequest,
    Plan,
    PlanRequest,
    SelectedSegment,
)
from .pacing_service import PacingService
from .reach_service import ReachFrequencyService

_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "creative_brief": {"type": "string"},
        "summary": {"type": "string"},
        "used_source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["creative_brief", "summary"],
}


class CampaignPlanService:
    """Build a cited campaign plan for an objective. Constructor takes explicit ports."""

    def __init__(
        self,
        audience: Any,
        llm: Any,
        guardrail: Any,
        tracer: Any,
        audit: Any,
        selection: AudienceSelectionService | None = None,
        allocation: BudgetAllocationService | None = None,
        reach: ReachFrequencyService | None = None,
        pacing: PacingService | None = None,
        review_router: Any = None,
    ) -> None:
        self._audience = audience
        self._llm = llm
        self._guardrail = guardrail
        self._tracer = tracer
        self._audit = audit
        self._selection = selection or AudienceSelectionService()
        self._allocation = allocation or BudgetAllocationService()
        self._reach = reach or ReachFrequencyService()
        self._pacing = pacing or PacingService()
        # Optional (rule R8): when bound, an escalated plan is routed to the Hrz7 maker-checker
        # console after it is audited. A run with no router still audits ESCALATED; it just is
        # not forwarded to a console.
        self._review_router = review_router

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def build_plan(self, request: PlanRequest, actor: str, tenant: str = "") -> Plan:
        with self._span("plan.build", market=request.market.value):
            self._guard(request.objective, Direction.INPUT, actor)

            segments = self._audience.segments(request.objective, request.market, request.vertical)
            selected = self._selection.select(segments, max_segments=request.max_segments)
            if not selected:
                raise NoAudienceError(
                    "no consented, reachable audience segment for "
                    f"{request.market.value}/{request.vertical.value}"
                )

            benchmarks = self._audience.channel_benchmarks(request.market, request.vertical)
            channel_mix = self._allocation.allocate(
                request.total_budget,
                benchmarks,
                request.market,
                request.vertical,
                channels=request.channels,
            )

            addressable = sum(s.segment.consented_reachable for s in selected)
            reach_frequency = self._reach.estimate(
                channel_mix,
                addressable,
                request.market,
                request.vertical,
                effective_frequency=request.effective_frequency,
            )

            flight = self._pacing.build(
                request.start_date,
                request.end_date,
                request.flight_legs,
                request.total_budget,
                request.pacing,
                request.market,
                request.vertical,
            )

            creative_brief, summary = self._draft(request, selected, channel_mix)

            citations = self._collect_citations(selected, channel_mix)
            plan = Plan(
                id=(
                    f"plan-{request.market.value}-{request.vertical.value}-"
                    f"{request.start_date.isoformat()}"
                ),
                objective=request.objective,
                market=request.market,
                vertical=request.vertical,
                total_budget=round(request.total_budget, 2),
                segments=selected,
                channel_mix=channel_mix,
                reach_frequency=reach_frequency,
                flight_schedule=flight,
                creative_brief=creative_brief,
                summary=summary,
                citations=citations,
                requires_human_review=True,
            )
            self._guard(summary, Direction.OUTPUT, actor)
            self._record(plan, actor)
            # Rule R8: route the escalated, already-audited plan to the Hrz7 maker-checker console.
            # Routing is a hand-off, never fatal to an already-assembled, already-audited plan.
            if self._review_router is not None and plan.requires_human_review:
                with contextlib.suppress(Exception):
                    self._review_router.route(plan, maker=actor, tenant=tenant)
            return plan

    # ------------------------------------------------------------------ #
    # LLM drafting (drafting only; never decides the numbers)
    # ------------------------------------------------------------------ #
    def _draft(
        self,
        request: PlanRequest,
        selected: tuple[SelectedSegment, ...],
        channel_mix: Any,
    ) -> tuple[str, str]:
        evidence = self._render_evidence(selected, channel_mix)
        prompt = (
            f"Draft a concise creative brief and a one-paragraph plan summary for the "
            f"campaign objective '{request.objective}' in market {request.market.value}, "
            f"vertical {request.vertical.value}. Use ONLY the deterministic plan facts "
            f"below; do not invent numbers. Cite the source ids you used.\n\n"
            f"PLAN FACTS:\n{evidence}"
        )
        response = self._llm.generate(
            LlmRequest(
                messages=(LlmMessage(role="user", content=prompt),),
                response_schema=_BRIEF_SCHEMA,
            )
        )
        return self._extract_draft(response.text, request)

    @staticmethod
    def _render_evidence(selected: tuple[SelectedSegment, ...], channel_mix: Any) -> str:
        lines: list[str] = []
        for s in selected:
            ids = " ".join(f"[{c.source_id} p.{c.page or 1}]" for c in s.citations)
            lines.append(
                f"{ids} segment {s.segment.name} (score {s.score:.2f}, "
                f"{s.segment.consented_reachable} consented-reachable)"
            )
        for line in channel_mix.lines:
            ids = " ".join(f"[{c.source_id} p.{c.page or 1}]" for c in line.citations)
            lines.append(
                f"{ids} channel {line.channel.value}: spend {line.amount:.0f} "
                f"({line.share * 100:.0f}%), {line.expected_conversions:.0f} conversions"
            )
        return "\n".join(lines) or "(no evidence)"

    @staticmethod
    def _extract_draft(text: str, request: PlanRequest) -> tuple[str, str]:
        fallback_brief = (
            f"Creative brief for {request.objective} in {request.market.value} "
            f"({request.vertical.value})."
        )
        fallback_summary = (
            f"Campaign plan for {request.objective} in {request.market.value} "
            f"({request.vertical.value}), budget {request.total_budget:.0f}."
        )
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return fallback_brief, fallback_summary
        brief = obj.get("creative_brief") if isinstance(obj, dict) else None
        summary = obj.get("summary") if isinstance(obj, dict) else None
        return (
            brief if isinstance(brief, str) and brief else fallback_brief,
            summary if isinstance(summary, str) and summary else fallback_summary,
        )

    # ------------------------------------------------------------------ #
    # Citation collection
    # ------------------------------------------------------------------ #
    @staticmethod
    def _collect_citations(
        selected: tuple[SelectedSegment, ...], channel_mix: Any
    ) -> tuple[Citation, ...]:
        seen: set[tuple[str, int | None]] = set()
        out: list[Citation] = []
        for s in selected:
            for c in s.citations:
                key = (c.source_id, c.page)
                if key not in seen:
                    seen.add(key)
                    out.append(c)
        for line in channel_mix.lines:
            for c in line.citations:
                key = (c.source_id, c.page)
                if key not in seen:
                    seen.add(key)
                    out.append(c)
        return tuple(out)

    # ------------------------------------------------------------------ #
    # Cross-cutting: guardrail, tracing, audit
    # ------------------------------------------------------------------ #
    def _guard(self, text: str, direction: Direction, actor: str) -> None:
        verdict: GuardrailVerdict = self._guardrail.screen(text, direction)
        if not verdict.allowed:
            self._audit.record(
                AuditEvent(
                    action="campaign_plan",
                    actor=actor,
                    decision=Decision.BLOCKED,
                    prompt=text if direction is Direction.INPUT else "",
                    response=text if direction is Direction.OUTPUT else "",
                    metadata={"reason": verdict.reason, "direction": direction.value},
                )
            )
            raise GuardrailBlockedError(verdict.reason or "guardrail blocked the request")

    def _span(self, name: str, **attrs: str) -> Any:
        try:
            return self._tracer.span(name, **attrs)
        except Exception:  # noqa: BLE001 - tracing must never break the pipeline
            return nullcontext()

    def _record(self, plan: Plan, actor: str) -> None:
        self._audit.record(
            AuditEvent(
                action="campaign_plan",
                actor=actor,
                decision=Decision.ESCALATED if plan.requires_human_review else Decision.ALLOWED,
                response=plan.summary,
                citations=plan.citations,
                metadata={
                    "market": plan.market.value,
                    "vertical": plan.vertical.value,
                    "objective": plan.objective,
                    "total_budget": f"{plan.total_budget:.2f}",
                },
            )
        )
