"""The ``live`` profile: the local open-weight model behind the LLM port, proved offline.

Every call goes through the shared ``hex_service_kit.localmodel`` client with a FAKE transport,
so this runs in the normal offline suite with no model server. What is proved: the request maps
onto chat messages with its temperature unchanged, a fenced and then schema-invalid answer is
retried until it validates, the response names the model that answered, the kit's two failure
types become the domain errors the API maps to 503 and 502, and the container builds every port
under ``live``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hex_service_kit.localmodel import LocalModelClient, LocalModelSettings
from tests.conftest import LOOPBACK_PEER, _settings

from campaign_planner.adapters.live.llm import LocalModelLLMAdapter
from campaign_planner.config import Container
from campaign_planner.domain.errors import ModelOutputError, ModelUnavailableError
from campaign_planner.domain.models import LlmMessage, LlmRequest

_SCHEMA = {
    "type": "object",
    "properties": {"creative_brief": {"type": "string"}, "summary": {"type": "string"}},
    "required": ["creative_brief", "summary"],
}
_ANSWERED_BY = "fake-org/fake-local-model"


class _FakeTransport:
    """Answers each POST with the next scripted content and records every request body."""

    def __init__(self, *answers: str, usage: dict[str, int] | None = None) -> None:
        self._answers = list(answers)
        self._usage = usage
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, url: str, body: bytes | None, timeout: float) -> bytes:
        assert body is not None
        self.bodies.append(json.loads(body))
        reply: dict[str, Any] = {
            "model": _ANSWERED_BY,
            "choices": [{"message": {"role": "assistant", "content": self._answers.pop(0)}}],
        }
        if self._usage is not None:
            reply["usage"] = self._usage
        return json.dumps(reply).encode()


def _adapter(transport: Any) -> LocalModelLLMAdapter:
    client = LocalModelClient(LocalModelSettings(url="http://127.0.0.1:1/x"), transport=transport)
    return LocalModelLLMAdapter(_settings("live"), client=client)


def _request(**overrides: Any) -> LlmRequest:
    fields: dict[str, Any] = {
        "messages": (LlmMessage(role="user", content="Draft the brief."),),
        "system_instruction": "You draft campaign briefs.",
        "temperature": 0.3,
        "max_output_tokens": 512,
        "response_schema": _SCHEMA,
    }
    fields.update(overrides)
    return LlmRequest(**fields)


def test_a_fenced_then_invalid_answer_is_retried_until_it_validates() -> None:
    transport = _FakeTransport(
        '```json\n{"creative_brief": "only half"}\n```',  # fenced, and missing `summary`
        '{"creative_brief": "Lead with the rate.", "summary": "Two segments, two channels."}',
        usage={"prompt_tokens": 40, "completion_tokens": 12},
    )

    response = _adapter(transport).generate(_request())

    assert len(transport.bodies) == 2, "the invalid first answer must be asked again"
    retry = transport.bodies[1]["messages"][-1]["content"]
    assert "summary" in retry, "the retry names the missing field"
    assert json.loads(response.text) == {
        "creative_brief": "Lead with the rate.",
        "summary": "Two segments, two channels.",
    }
    assert response.raw == json.loads(response.text)
    assert response.model == _ANSWERED_BY
    assert (response.usage.input_tokens, response.usage.output_tokens) == (80, 24)


def test_the_request_maps_onto_chat_messages_with_its_temperature_unchanged() -> None:
    transport = _FakeTransport("A plain narrative.")

    response = _adapter(transport).generate(_request(response_schema=None))

    body = transport.bodies[0]
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 512
    assert body["messages"] == [
        {"role": "system", "content": "You draft campaign briefs."},
        {"role": "user", "content": "Draft the brief."},
    ]
    assert response.text == "A plain narrative."
    # MLX reports no usage; LlmResponse requires one, so it reads as zeros, never invented counts.
    assert (response.usage.input_tokens, response.usage.output_tokens) == (0, 0)


def test_an_answer_that_never_validates_is_a_model_output_error() -> None:
    transport = _FakeTransport("not json", "still not json", "nope")
    with pytest.raises(ModelOutputError):
        _adapter(transport).generate(_request())
    assert len(transport.bodies) == 3


def test_an_unreachable_server_is_a_model_unavailable_error_naming_the_recipe() -> None:
    def refused(url: str, body: bytes | None, timeout: float) -> bytes:
        raise ConnectionRefusedError("connection refused")

    with pytest.raises(ModelUnavailableError, match="mlx_vlm.server"):
        _adapter(refused).generate(_request())


def test_classify_coerces_the_answer_to_a_label() -> None:
    transport = _FakeTransport("Label: Banking.")
    assert _adapter(transport).classify("text", ["retail", "banking"]) == "banking"
    assert transport.bodies[0]["temperature"] == 0.0


def test_the_container_builds_every_port_under_live() -> None:
    container = Container(_settings("live"))
    ports = [name for name in _settings("live").adapters if name]
    assert ports, "no port is bound, so this test would prove nothing"
    for port in ports:
        assert getattr(container, port) is not None, port
    assert isinstance(container.llm, LocalModelLLMAdapter)


def test_the_api_answers_503_when_the_live_model_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from campaign_planner.api import app as app_module
    from campaign_planner.api import deps

    container = Container(_settings("live"))

    def refused(url: str, body: bytes | None, timeout: float) -> bytes:
        raise ConnectionRefusedError("connection refused")

    container.__dict__["llm"] = _adapter(refused)
    monkeypatch.setattr(deps, "get_container", lambda: container)
    client = TestClient(app_module.app, client=LOOPBACK_PEER)
    reply = client.post(
        "/v1/plan",
        json={
            "objective": "savings account acquisition",
            "market": "SG",
            "vertical": "banking",
            "total_budget": 120000,
            "start_date": "2026-10-01",
            "end_date": "2026-12-31",
        },
    )
    assert reply.status_code == 503, reply.text
    assert "model unavailable" in reply.json()["detail"]


def test_the_pill_names_the_local_model_under_live(monkeypatch: pytest.MonkeyPatch) -> None:
    """``live`` runs on the laptop and a real model answers, so neither stub string is true."""
    monkeypatch.setenv("LOCAL_MODEL", _ANSWERED_BY)
    settings = _settings("live")
    assert settings.runtime == "local"
    assert settings.generator_model == _ANSWERED_BY
