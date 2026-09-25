"""The console's model pill names the model that ANSWERED, and the service is where that is true.

Owner decision, 2026-09-23: every console shows two small pills at the top right, the model
that answered and ``Search`` when an online search tool was used. The service carries both on
the response that answered (``X-Answered-By`` / ``X-Search-Used``, via
``hex_service_kit.web.install_answer_provenance``), because only the call that produced an answer
knows what produced it. ``/healthz`` states what configuration WOULD call, which is the pill's
starting value and nothing more.

What is held here, offline:

* a model-backed route answered under ``local`` names the offline stub, the same string
  ``generator_model`` reports, and never a Gemini id for a request that never left the machine;
* a route that called no model sends neither header, so a pill never invents one;
* a call that noted a search sends ``X-Search-Used: true`` through the real middleware;
* the managed adapter notes the model it actually passed to the client, and that model is the
  one ``generator_model`` reports under ``gcp``, with no flag left that could move one and not
  the other;
* the cross-origin console can READ both headers (the middleware exposes them).
"""

from __future__ import annotations

import sys
import types as pytypes
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance
from tests.conftest import LOOPBACK_PEER, _settings

from campaign_planner.adapters.gcp.gemini_llm import GeminiLLMAdapter
from campaign_planner.adapters.local.llm import LocalDeterministicLLMAdapter
from campaign_planner.api import deps
from campaign_planner.api.app import app
from campaign_planner.config import Container, ModelSettings
from campaign_planner.domain.models import LlmMessage, LlmRequest, LlmResponse

_PLAN_BODY: dict[str, Any] = {
    "objective": "savings account acquisition",
    "market": "SG",
    "vertical": "banking",
    "total_budget": 120000,
    "start_date": "2026-07-01",
    "end_date": "2026-07-28",
}


def _client(container: Container, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app, client=LOOPBACK_PEER)


def test_a_local_plan_is_answered_by_the_offline_stub_the_health_check_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings("local")
    reply = _client(Container(settings), monkeypatch).post("/v1/plan", json=_PLAN_BODY)
    assert reply.status_code == 200, reply.text
    assert reply.headers.get("x-answered-by") == settings.generator_model
    assert settings.generator_model == LocalDeterministicLLMAdapter.STUB_NAME
    assert "x-search-used" not in reply.headers, "nothing searched, so nothing may claim it"


def test_a_route_that_called_no_model_names_none(monkeypatch: pytest.MonkeyPatch) -> None:
    reply = _client(Container(_settings("local")), monkeypatch).get("/healthz")
    assert reply.status_code == 200
    assert "x-answered-by" not in reply.headers
    assert "x-search-used" not in reply.headers


class _SearchingLlm:
    """A model port whose call attached an online search tool, as a grounded adapter would."""

    def generate(self, request: LlmRequest) -> LlmResponse:
        provenance.note_model("fake-grounded-model")
        provenance.note_search()
        return LlmResponse(text='{"creative_brief": "b", "summary": "s"}', model="fake")

    def classify(self, text: str, labels: list[str]) -> str:
        return labels[0]


def test_a_call_that_searched_says_so_on_the_response(monkeypatch: pytest.MonkeyPatch) -> None:
    container = Container(_settings("local"))
    container.__dict__["llm"] = _SearchingLlm()
    reply = _client(container, monkeypatch).post("/v1/plan", json=_PLAN_BODY)
    assert reply.status_code == 200, reply.text
    assert reply.headers.get("x-answered-by") == "fake-grounded-model"
    assert reply.headers.get("x-search-used") == "true"


def test_the_cross_origin_console_can_read_both_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console calls this service directly; a header CORS does not expose is invisible to it."""
    reply = _client(Container(_settings("local")), monkeypatch).post("/v1/plan", json=_PLAN_BODY)
    exposed = {
        name.strip().lower()
        for value in reply.headers.get_list("access-control-expose-headers")
        for name in value.split(",")
    }
    assert {"x-answered-by", "x-search-used"} <= exposed


# --------------------------------------------------------------------------- #
# The managed adapter, against a faked SDK surface (no google-genai installed)
# --------------------------------------------------------------------------- #
class _Recorder:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def _fake_types() -> Any:
    fake = pytypes.SimpleNamespace()
    fake.Content = _Recorder
    fake.Part = pytypes.SimpleNamespace(from_text=lambda text: _Recorder(text=text))
    fake.GenerateContentConfig = _Recorder
    fake.ThinkingConfig = _Recorder
    fake.ThinkingLevel = pytypes.SimpleNamespace(LOW="LOW", HIGH="HIGH")
    return fake


class _FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return pytypes.SimpleNamespace(text="banking", usage_metadata=None)


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch) -> tuple[GeminiLLMAdapter, _FakeModels]:
    fake_genai = pytypes.ModuleType("google.genai")
    fake_genai.types = _fake_types()  # type: ignore[attr-defined]
    if "google" not in sys.modules:
        monkeypatch.setitem(sys.modules, "google", pytypes.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    adapter = GeminiLLMAdapter(_settings("gcp"))
    models = _FakeModels()
    adapter._client = pytypes.SimpleNamespace(models=models)
    return adapter, models


def _request(**overrides: Any) -> LlmRequest:
    return LlmRequest(messages=(LlmMessage(role="user", content="Draft."),), **overrides)


def test_the_managed_adapter_notes_the_model_it_called(
    gemini: tuple[GeminiLLMAdapter, _FakeModels],
) -> None:
    adapter, models = gemini
    with provenance.scope() as record:
        adapter.generate(_request())
    assert models.calls[0]["model"] == record.models[0]
    assert record.models == [_settings("gcp").generator_model]
    assert record.search_used is False, "no search tool is attached to this call"


def test_the_managed_adapter_notes_the_triage_model_on_classify(
    gemini: tuple[GeminiLLMAdapter, _FakeModels],
) -> None:
    adapter, models = gemini
    with provenance.scope() as record:
        assert adapter.classify("text", ["retail", "banking"]) == "banking"
    assert record.models == [models.calls[0]["model"]]
    assert models.calls[0]["config"].kwargs["temperature"] == 0.0, "classification stays pinned"


def test_generator_model_is_the_model_the_managed_adapter_calls() -> None:
    settings = _settings("gcp")
    assert settings.generator_model == settings.models.reasoning
    assert not hasattr(ModelSettings(), "use_hard_reasoning"), (
        "a flag that moved the reported model without moving the adapter's is back"
    )
    assert not hasattr(ModelSettings(), "hard_reasoning")
