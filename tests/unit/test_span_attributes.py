"""The plan pipeline opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail: it has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit
store. The value of tracing the plan pipeline therefore depends on the span carrying
structural attributes only (which market), never the objective text, a segment title or any
identifier a marketer typed into the request.

The shared ``local_container`` fixture's tracer only records span NAMES, so a leaked
attribute would be invisible to it; this module swaps in a tracer that records the
attributes too, and drives the real :class:`CampaignPlanService` pipeline through it with a
planted, obviously fictional identifier in the objective so a leak would actually show.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from campaign_planner.config import Container
from campaign_planner.domain.models import Market, PacingStrategy, PlanRequest, Vertical
from campaign_planner.domain.services import CampaignPlanService

#: The one span the pipeline opens, and the full attribute set it may carry.
_EXPECTED_SPAN = "plan.build"
_ALLOWED_ATTRIBUTES = frozenset({"market"})

#: Planted content markers (all obviously fictional). If any span attribute value carried
#: the request content, these would surface in the recorded attributes.
_PLANTED_IDENTIFIER = "S1234567D"
_PLANTED_OBJECTIVE = (
    f"savings account acquisition for customer {_PLANTED_IDENTIFIER} (PLANTED, FICTIONAL)"
)


class _RecordingTracer:
    """Records every span name AND its attributes, unlike the name-only conftest recorder."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str):  # type: ignore[no-untyped-def]
        self.spans.append((name, dict(attributes)))
        yield


def _build_plan(local_container: Container) -> _RecordingTracer:
    tracer = _RecordingTracer()
    service = CampaignPlanService(
        audience=local_container.audience,
        llm=local_container.llm,
        guardrail=local_container.guardrail,
        tracer=tracer,
        audit=local_container.audit,
    )
    request = PlanRequest(
        objective=_PLANTED_OBJECTIVE,
        market=Market.SG,
        vertical=Vertical.BANKING,
        total_budget=120_000.0,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 28),
        pacing=PacingStrategy.EVEN,
    )
    service.build_plan(request, actor="span-test-bot (FICTIONAL)")
    return tracer


def test_building_a_plan_opens_exactly_one_named_span(local_container: Container) -> None:
    tracer = _build_plan(local_container)
    assert [name for name, _ in tracer.spans] == [_EXPECTED_SPAN]


def test_the_span_attribute_set_is_a_fixed_allowlist(local_container: Container) -> None:
    """A plan must not start attaching request content to the span to explain itself."""
    tracer = _build_plan(local_container)
    for name, attributes in tracer.spans:
        assert set(attributes) == _ALLOWED_ATTRIBUTES, name


def test_no_span_attribute_value_carries_request_content(local_container: Container) -> None:
    """The objective carries a planted fictional identifier, so a leak would show here."""
    tracer = _build_plan(local_container)
    emitted = " ".join(value for _, attributes in tracer.spans for value in attributes.values())
    assert _PLANTED_IDENTIFIER not in emitted
    assert _PLANTED_IDENTIFIER.lower() not in emitted.lower()
    assert _PLANTED_OBJECTIVE not in emitted


def test_the_market_attribute_is_structural_not_content(local_container: Container) -> None:
    """The one allowed attribute answers "which market", nothing about the request text."""
    _, attributes = _build_plan(local_container).spans[0]
    assert attributes["market"] == Market.SG.value
