"""Sampling is decided per call site: pinned where output is compared, free where it is prose.

History. On 2026-08-26 two runs of one identical case against the `cdd-sow-research` deployment
returned different scores minutes apart, because the shared request builder defaulted to
`temperature=0.2` and every grounded call sampled. The fleet's answer was to pin `0.0` on the
request TYPE, so a call site that omitted it could not sample.

What changed (owner decision, 2026-09-23). A blanket pin also pinned drafting and narration,
where sampling is the point, and some models (Opus 5, Fable 5) reject the parameter outright,
so "free" cannot be spelled `1.0`: it has to be the parameter's absence. So the type's default is
now `None` (send nothing), and each call site states its choice. `0.0` stays wherever the output
is extracted, classified, scored or compared against a deterministic check.

This service's only generation call drafts the creative brief and narrates the plan summary over
numbers the deterministic engines already fixed, so it is FREE. Classification stays PINNED in
both model adapters.

**Temperature 0 is not a promise of determinism, and nothing here asserts one.** A hosted model
can still vary across batching and model revisions.
"""

from __future__ import annotations

import json
import types as pytypes
from datetime import date
from typing import Any

import pytest
from tests.conftest import _settings

from campaign_planner.adapters.gcp.gemini_llm import GeminiLLMAdapter
from campaign_planner.config import Container
from campaign_planner.domain.models import (
    LlmMessage,
    LlmRequest,
    LlmResponse,
    Market,
    PlanRequest,
    Vertical,
)
from campaign_planner.domain.services import CampaignPlanService


def test_the_request_type_leaves_sampling_to_the_call_site() -> None:
    assert LlmRequest.__dataclass_fields__["temperature"].default is None


class _RecordingLlm:
    def __init__(self) -> None:
        self.requests: list[LlmRequest] = []

    def generate(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        body = {"creative_brief": "b", "summary": "s", "used_source_ids": []}
        return LlmResponse(text=json.dumps(body), raw=body)

    def classify(self, text: str, labels: list[str]) -> str:
        return labels[0]


def test_the_brief_and_summary_draft_sends_no_temperature(local_container: Container) -> None:
    recorder = _RecordingLlm()
    service = CampaignPlanService(
        audience=local_container.audience,
        llm=recorder,
        guardrail=local_container.guardrail,
        tracer=local_container.tracer,
        audit=local_container.audit,
    )
    service.build_plan(
        PlanRequest(
            objective="savings account acquisition",
            market=Market.SG,
            vertical=Vertical.BANKING,
            total_budget=120000.0,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 28),
        ),
        actor="demo.analyst@bank.example",
    )
    assert recorder.requests, "the plan was built without drafting, so this proves nothing"
    assert all(r.temperature is None for r in recorder.requests)


class _Recorder:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@pytest.fixture
def gemini_config() -> Any:
    fake = pytypes.SimpleNamespace(
        GenerateContentConfig=_Recorder,
        ThinkingConfig=_Recorder,
        ThinkingLevel=pytypes.SimpleNamespace(LOW="LOW", HIGH="HIGH"),
    )
    adapter = GeminiLLMAdapter(_settings("gcp"))
    return lambda request: adapter._build_config(request, fake).kwargs


def test_the_managed_adapter_omits_a_free_temperature(gemini_config: Any) -> None:
    request = LlmRequest(messages=(LlmMessage(role="user", content="Draft."),))
    assert "temperature" not in gemini_config(request), "free must be absent, never 1.0"


def test_the_managed_adapter_keeps_a_pinned_temperature(gemini_config: Any) -> None:
    request = LlmRequest(messages=(LlmMessage(role="user", content="x"),), temperature=0.0)
    assert gemini_config(request)["temperature"] == 0.0
