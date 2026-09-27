"""The Model Armor adapter blocks on a match, and fails closed on no verdict or an API error.

It also fails closed on an INCOMPLETE screen: ``invocationResult`` ``PARTIAL`` or ``FAILURE``
means some or all filters were skipped or failed, and a skipped filter reports
``NO_MATCH_FOUND``. Padding a prompt past the prompt-injection filter's token limit would
otherwise get it through unscreened, so only ``NO_MATCH_FOUND`` with ``SUCCESS`` allows.

The adapter speaks Model Armor's REST API, so the verdict is read from JSON, where enums are
their member NAMES. The old rule, ``match_state != "MATCH_FOUND"`` (or "no findings" when the
state was absent), allowed ``FILTER_MATCH_STATE_UNSPECIFIED``, an empty or missing
``sanitizationResult``, and ``NO_MATCH_FOUND`` from a ``PARTIAL`` or ``FAILURE`` screen.

This module tests at two levels:

* **SDK-free** (always runs, including CI's SDK-free ``[dev]`` gate): responses are the JSON
  shape Model Armor returns, built from ``_MirrorState`` / ``_MirrorInvocation``, stdlib
  enums with the real member names and numbers, and screened through ``screen()`` with a
  fake HTTP client returning real ``httpx.Response`` objects, so nothing touches the network.
* **Real SDK** (runs where ``google-cloud-modelarmor`` is installed, skips otherwise): the
  responses are real ``modelarmor_v1`` messages serialised with the proto3 JSON mapping, the
  exact wire shape the REST endpoint returns. The first of these tests also pins the mirror
  to the real enums, so the SDK-free half cannot drift.
"""

from __future__ import annotations

import enum
import json
from typing import Any

import httpx
import pytest

from campaign_planner.adapters.gcp.model_armor_guardrail import ModelArmorGuardrailAdapter
from campaign_planner.config import Settings
from campaign_planner.domain.models import Direction

TEXT = "Plan a Q3 savings-account campaign for young professionals."
DIRECTIONS = [Direction.INPUT, Direction.OUTPUT]


class _MirrorState(enum.IntEnum):
    """``modelarmor_v1.FilterMatchState``'s members, by name and number."""

    FILTER_MATCH_STATE_UNSPECIFIED = 0
    NO_MATCH_FOUND = 1
    MATCH_FOUND = 2


class _MirrorInvocation(enum.IntEnum):
    """``modelarmor_v1.InvocationResult``'s members, by name and number."""

    INVOCATION_RESULT_UNSPECIFIED = 0
    SUCCESS = 1
    PARTIAL = 2
    FAILURE = 3


class _FakeHttp:
    """Stands in for ``httpx.Client``: returns a canned JSON body, or a canned status."""

    def __init__(self, body: Any = None, status: int = 200, error: Exception | None = None):
        self._body = body
        self._status = status
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: Any, headers: Any, timeout: Any) -> httpx.Response:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self._error is not None:
            raise self._error
        return httpx.Response(self._status, json=self._body, request=httpx.Request("POST", url))


def _adapter(http: _FakeHttp) -> ModelArmorGuardrailAdapter:
    adapter = ModelArmorGuardrailAdapter(Settings(project_id="p", profile="gcp"))
    adapter._client = http  # skip the real client; the mapping is what is under test
    adapter._bearer_token = lambda: "test-token"  # type: ignore[method-assign]
    return adapter


def _screen(body: Any, direction: Direction = Direction.INPUT) -> Any:
    return _adapter(_FakeHttp(body)).screen(TEXT, direction)


def _mirror_body(
    state: _MirrorState | None, invocation: _MirrorInvocation | None = _MirrorInvocation.SUCCESS
) -> dict[str, Any]:
    """The REST JSON shape, enums as names; ``None`` leaves that field out."""
    result: dict[str, Any] = {}
    if state is not None:
        result["filterMatchState"] = state.name
    if invocation is not None:
        result["invocationResult"] = invocation.name
    return {"sanitizationResult": result}


# --------------------------------------------------------------------------- #
# SDK-free: the mapping, through screen(), on the REST JSON shape
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_match_found_blocks_sdk_free(direction: Direction) -> None:
    verdict = _screen(_mirror_body(_MirrorState.MATCH_FOUND), direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert verdict.findings


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_no_match_found_with_success_allows_sdk_free(direction: Direction) -> None:
    verdict = _screen(_mirror_body(_MirrorState.NO_MATCH_FOUND), direction)
    assert verdict.allowed is True
    assert verdict.sanitized_text == TEXT
    assert verdict.findings == ()


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("invocation", list(_MirrorInvocation), ids=lambda m: m.name)
def test_match_found_blocks_however_many_filters_ran_sdk_free(
    direction: Direction, invocation: _MirrorInvocation
) -> None:
    verdict = _screen(_mirror_body(_MirrorState.MATCH_FOUND, invocation), direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize(
    "invocation",
    [
        _MirrorInvocation.PARTIAL,
        _MirrorInvocation.FAILURE,
        _MirrorInvocation.INVOCATION_RESULT_UNSPECIFIED,
        None,
    ],
    ids=["PARTIAL", "FAILURE", "UNSPECIFIED", "absent"],
)
def test_no_match_from_an_incomplete_screen_blocks_sdk_free(
    direction: Direction, invocation: _MirrorInvocation | None
) -> None:
    """A skipped filter reports no match. That is not a pass: the text was not screened."""
    verdict = _screen(_mirror_body(_MirrorState.NO_MATCH_FOUND, invocation), direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert "no complete filter decision" in verdict.reason


def test_exactly_one_combination_allows_sdk_free() -> None:
    allowed = [
        (state.name, invocation.name)
        for state in _MirrorState
        for invocation in _MirrorInvocation
        if _screen(_mirror_body(state, invocation)).allowed
    ]
    assert allowed == [("NO_MATCH_FOUND", "SUCCESS")]


@pytest.mark.parametrize(
    "body",
    [
        _mirror_body(_MirrorState.FILTER_MATCH_STATE_UNSPECIFIED),
        _mirror_body(None),
        {"sanitizationResult": {}},
        {"sanitizationResult": None},
        {},
        # A number is not the JSON mapping's enum encoding; it must not read as a verdict.
        {"sanitizationResult": {"filterMatchState": 1, "invocationResult": 1}},
        {
            "sanitizationResult": {
                "filterMatchState": "no_match_found",
                "invocationResult": "SUCCESS",
            }
        },
        [],
    ],
    ids=[
        "unspecified-state",
        "absent-state",
        "empty-result",
        "null-result",
        "missing-result",
        "integer-enums",
        "wrong-case",
        "non-object-body",
    ],
)
def test_no_verdict_fails_closed_sdk_free(body: Any) -> None:
    verdict = _screen(body)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_call_carries_the_deadline_sdk_free(direction: Direction) -> None:
    http = _FakeHttp(_mirror_body(_MirrorState.NO_MATCH_FOUND))
    _adapter(http).screen(TEXT, direction)
    assert [c["timeout"] for c in http.calls] == [Settings().model_armor.timeout_seconds]
    assert http.calls[0]["timeout"] > 0


@pytest.mark.parametrize("status", [400, 403, 429, 500, 503])
def test_an_http_error_propagates_sdk_free(status: int) -> None:
    """A non-2xx answer must not turn into an allow; it reaches the caller."""
    http = _FakeHttp({"error": {"code": status}}, status=status)
    with pytest.raises(httpx.HTTPStatusError):
        _adapter(http).screen(TEXT, Direction.INPUT)


def test_a_timeout_propagates_sdk_free() -> None:
    http = _FakeHttp(error=httpx.ReadTimeout("Model Armor did not answer"))
    with pytest.raises(httpx.ReadTimeout):
        _adapter(http).screen(TEXT, Direction.OUTPUT)


# --------------------------------------------------------------------------- #
# Real SDK: real modelarmor_v1 messages, serialised to the REST wire shape
# --------------------------------------------------------------------------- #
def _ma() -> Any:
    return pytest.importorskip("google.cloud.modelarmor_v1")


def _real_body(
    direction: Direction,
    state_name: str | None,
    invocation_name: str = "SUCCESS",
    *,
    skipped: bool = False,
) -> Any:
    """A real sanitize response as REST JSON; ``state_name=None`` leaves the result unset.

    ``skipped`` adds the prompt-injection filter as not having run, the shape a prompt padded
    past that filter's token limit produces.
    """
    ma = _ma()
    cls = (
        ma.SanitizeUserPromptResponse
        if direction is Direction.INPUT
        else ma.SanitizeModelResponseResponse
    )
    if state_name is None:
        message = cls()
    else:
        filter_results = {}
        if skipped:
            filter_results["pi_and_jailbreak"] = ma.FilterResult(
                pi_and_jailbreak_filter_result=ma.PiAndJailbreakFilterResult(
                    execution_state=ma.FilterExecutionState.EXECUTION_SKIPPED,
                    match_state=ma.FilterMatchState.NO_MATCH_FOUND,
                )
            )
        message = cls(
            sanitization_result=ma.SanitizationResult(
                filter_match_state=ma.FilterMatchState[state_name],
                invocation_result=ma.InvocationResult[invocation_name],
                filter_results=filter_results,
            )
        )
    # The proto3 JSON mapping, as the REST endpoint emits it: enum NAMES, camelCase fields.
    return json.loads(cls.to_json(message, use_integers_for_enums=False))


@pytest.mark.parametrize(
    ("mirror", "real_name"),
    [(_MirrorState, "FilterMatchState"), (_MirrorInvocation, "InvocationResult")],
    ids=["FilterMatchState", "InvocationResult"],
)
def test_the_mirror_matches_the_real_enum(mirror: Any, real_name: str) -> None:
    real = getattr(_ma(), real_name)
    assert {m.name: int(m) for m in real} == {m.name: int(m) for m in mirror}


def test_the_real_wire_shape_matches_the_mirror_body() -> None:
    """The SDK-free half's hand-built JSON carries the verdict where the real messages do."""
    real = _real_body(Direction.INPUT, "NO_MATCH_FOUND", "PARTIAL")["sanitizationResult"]
    mirror = _mirror_body(_MirrorState.NO_MATCH_FOUND, _MirrorInvocation.PARTIAL)
    verdict_fields = ("filterMatchState", "invocationResult")
    assert {k: real[k] for k in verdict_fields} == mirror["sanitizationResult"]


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_match_found_blocks(direction: Direction) -> None:
    http = _FakeHttp(_real_body(direction, "MATCH_FOUND"))
    verdict = _adapter(http).screen(TEXT, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert len(http.calls) == 1


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_no_match_found_with_success_allows(direction: Direction) -> None:
    verdict = _screen(_real_body(direction, "NO_MATCH_FOUND"), direction)
    assert verdict.allowed is True
    assert verdict.sanitized_text == TEXT


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize(
    "state_name",
    [None, "FILTER_MATCH_STATE_UNSPECIFIED"],
    ids=["missing-result", "unspecified-state"],
)
def test_no_verdict_fails_closed(direction: Direction, state_name: str | None) -> None:
    verdict = _screen(_real_body(direction, state_name), direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("invocation_name", ["PARTIAL", "FAILURE", "INVOCATION_RESULT_UNSPECIFIED"])
def test_no_match_from_a_screen_where_filters_did_not_run_blocks(
    direction: Direction, invocation_name: str
) -> None:
    body = _real_body(direction, "NO_MATCH_FOUND", invocation_name, skipped=True)
    verdict = _screen(body, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert "no complete filter decision" in verdict.reason


def test_api_errors_propagate() -> None:
    """An API failure must not turn into an allow; it reaches the caller."""
    _ma()
    http = _FakeHttp(_real_body(Direction.INPUT, "NO_MATCH_FOUND"), status=503)
    with pytest.raises(httpx.HTTPStatusError):
        _adapter(http).screen(TEXT, Direction.INPUT)
