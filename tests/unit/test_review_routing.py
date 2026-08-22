"""R8 routing: an escalated campaign plan is routed to Hrz7 via the shared review-kit.

Every campaign plan is spend-affecting and always requires human review, so rule R8 says it MUST
be handed to the Hrz7 maker-checker console rather than left as a per-repo boolean. These tests
prove the producer half of that loop end-to-end against the offline local router (an in-memory
outbox), and prove the redact-before-wire boundary so no stray contact identifier reaches the
console. All data here is fictional.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from campaign_planner.adapters._review_payload import plan_to_review
from campaign_planner.adapters.local.review_router import LocalReviewRouter
from campaign_planner.config import Container, Settings
from campaign_planner.domain.models import (
    Citation,
    Market,
    PacingStrategy,
    Plan,
    PlanRequest,
    SourceType,
    Vertical,
)
from campaign_planner.domain.services import CampaignPlanService

ACTOR = "planner@bank.test"
TENANT = "demo-bank"
START = date(2026, 7, 1)
END = date(2026, 7, 28)


def _service_with_router(container: Container, router: object | None) -> CampaignPlanService:
    return CampaignPlanService(
        audience=container.audience,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
        review_router=router,
    )


def _request() -> PlanRequest:
    return PlanRequest(
        objective="savings account acquisition",
        market=Market.SG,
        vertical=Vertical.BANKING,
        total_budget=120_000.0,
        start_date=START,
        end_date=END,
        pacing=PacingStrategy.EVEN,
    )


def test_build_plan_routes_escalated_plan_to_outbox(
    local_container: Container, local_settings: Settings
):
    """A completed plan enqueues exactly one review to the router's outbox (R8)."""
    router = LocalReviewRouter(local_settings)
    service = _service_with_router(local_container, router)
    assert not router.outbox.pending()

    plan = service.build_plan(_request(), actor=ACTOR, tenant=TENANT)
    assert plan.requires_human_review

    pending = router.outbox.pending()
    assert len(pending) == 1, "the escalated plan must be routed to Hrz7 exactly once"
    review = pending[0].review
    assert review.action == "campaign_plan:build"
    assert review.case_ref == plan.id
    assert review.maker == ACTOR
    assert review.tenant == TENANT


def _plan_with_contact_pii(base: Plan) -> Plan:
    """Add a fictional email to the objective and to a citation snippet, so redaction is proven."""
    contact_cite = Citation(
        source_id="seed-partner",
        source_type=SourceType.BENCHMARK,
        title="Partner rate card",
        snippet="Contact the partner desk at rates@partner.test for the current CPMs.",
    )
    return replace(
        base,
        objective="promo for the desk@agency.test distribution list",
        citations=(*base.citations, contact_cite),
    )


def test_payload_is_redacted_and_carries_tenant_and_severity(local_container: Container):
    """The wire payload masks contact ids, carries the tenant, and dual-controls spend (R8)."""
    base = _service_with_router(local_container, None).build_plan(_request(), actor=ACTOR)
    review = plan_to_review(_plan_with_contact_pii(base), maker=ACTOR, tenant=TENANT)

    assert review.tenant == TENANT
    # The Plan carries no severity signal, so MEDIUM is the conservative default R8 routes on.
    assert review.severity == "medium"
    # A budget commitment always warrants four-eyes (maker proposes, checker disposes).
    assert review.required_approvals == 2
    assert review.sod_group == "campaign-maker-checker"
    # No raw email survives into the descriptor the console receives.
    assert "desk@agency.test" not in review.subject
    assert "[EMAIL]" in review.subject
    for citation in review.citations:
        assert "rates@partner.test" not in citation.snippet
    assert any(c.title == "Partner rate card" for c in review.citations)


def test_no_router_still_builds_plan(local_container: Container):
    """Routing is optional: with no router bound, planning still returns an escalated plan."""
    plan = _service_with_router(local_container, None).build_plan(_request(), actor=ACTOR)
    assert plan.requires_human_review


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
