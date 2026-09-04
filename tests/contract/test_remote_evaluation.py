"""Contract test: the platform evaluation adapter speaks the hardened model-quality-gate protocol.

``RemoteEvaluationAdapter`` (``EvaluationGatePort``) is a thin HTTP client for the shared
model-quality-gate AI-quality service. These tests pin the wire contract with ``respx`` (a dev
dependency) against the agent-eval-kit ``PromotionGateClient``, which refuses thin evidence:

* ``POST /v1/evaluations`` carries a structured ``target`` and a top-level ``dataset_id``
  that equals ``target.dataset_id``, selects metrics only via ``bundle == "mkt2-campaign"``
  (never a metric-name list), and parses the ``results`` array into an :class:`EvalReport`.
  The response must carry ``n_examples`` plus durable ``run_id`` / ``dataset_digest`` /
  ``evaluator`` identifiers, and each row's ``passed`` must agree with score vs threshold.
* ``POST /v1/gate`` (POST, not GET) returns the full GateDecision (attested eval evidence,
  a consistent red-team report, model-card and MRM references) and yields its aggregate.
  A bare ``{"passed": <bool>}`` is no longer accepted; a FAIL must be reached through
  consistent evidence, never a contradictory body.
* A non-2xx response or inconsistent evidence raises :class:`RemoteEvaluationError`.

All identifiers in the fixtures are obviously fictional.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from campaign_planner.adapters.platform.remote_evaluation import (
    RemoteEvaluationAdapter,
    RemoteEvaluationError,
)
from campaign_planner.config import Settings
from campaign_planner.domain.models import EvalReport

_BASE = "http://localhost:8084"
# A path with directories and a compound stem proves basename + only-``.jsonl`` stripping.
_DATASET_PATH = "/data/eval/plans.golden.jsonl"
_DATASET_ID = "plans.golden"


def _adapter() -> RemoteEvaluationAdapter:
    return RemoteEvaluationAdapter(Settings())


def _eval_body(*, citation_passed: bool = False) -> dict[str, object]:
    """A contract-consistent evaluation body: rows agree with their scores, evidence is durable."""
    return {
        "results": [
            {
                "metric": "plan_groundedness",
                "score": 0.91,
                "threshold": 0.80,
                "passed": True,
            },
            {
                "metric": "citation_accuracy",
                "score": 0.92 if citation_passed else 0.88,
                "threshold": 0.90,
                "passed": citation_passed,
            },
        ],
        "n_examples": 6,
        "run_id": "run-fictional-0001",
        "dataset_digest": "sha256:feedfacefeedfacefeedfacefeedfacefeedface",
        "evaluator": "hrz4-quality.example",
        "artifact_refs": ["gs://fictional-hrz4-evidence/run-fictional-0001/report.json"],
        "attested": True,
    }


def _gate_body(*, eval_passed: bool, redteam_passed: bool = True) -> dict[str, object]:
    """A full, internally consistent GateDecision (the only shape the client accepts)."""
    return {
        "passed": eval_passed and redteam_passed,
        "eval_report": _eval_body(citation_passed=eval_passed),
        "redteam_report": {
            "passed": redteam_passed,
            "results": [
                {"probe": "prompt-injection", "passed": redteam_passed, "blocked": redteam_passed},
                {"probe": "data-exfiltration", "passed": True, "blocked": True},
            ],
        },
        "model_card_ref": "gs://fictional-hrz4-evidence/model-cards/mkt2-campaign.md",
        "mrm_evidence_ref": "https://mrm.example/evidence/run-fictional-0001",
    }


@respx.mock
def test_evaluate_posts_hrz4_contract_and_parses_results() -> None:
    route = respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json=_eval_body())
    )

    report = _adapter().evaluate(_DATASET_PATH)

    # The request matched /v1/evaluations exactly once.
    assert route.called
    sent = json.loads(route.calls.last.request.content)

    # Structured target with the pinned model + stable prompt version.
    assert sent["target"] == {
        "model": Settings().models.reasoning,
        "prompt_version": "v1",
        "dataset_id": _DATASET_ID,
        "system": "",
    }
    # Top-level dataset_id must equal target.dataset_id (model-quality-gate 422s on divergence).
    assert sent["dataset_id"] == sent["target"]["dataset_id"] == _DATASET_ID
    # Metrics are selected ONLY by the bundle — never a metric-name list.
    assert sent["bundle"] == "mkt2-campaign"
    assert "metrics" not in sent
    assert "metrics" not in sent["target"]
    assert set(sent) == {"target", "dataset_id", "bundle"}

    # The results array is parsed into the domain EvalReport.
    assert isinstance(report, EvalReport)
    assert report.dataset == _DATASET_ID
    assert report.n_examples == 6
    assert [r.metric for r in report.results] == ["plan_groundedness", "citation_accuracy"]
    assert report.results[0].score == pytest.approx(0.91)
    assert report.results[0].threshold == pytest.approx(0.80)
    assert report.results[0].passed is True
    assert report.results[1].passed is False
    # One metric failed => the report fails (gates promotion).
    assert report.passed is False


@respx.mock
def test_attested_evidence_survives_the_adapter() -> None:
    """The adapter must not rebuild the report, because a rebuild drops the evidence.

    This adapter used to map the package's report onto a hand-copied three-field domain
    ``EvalReport``, which is a lossy identity function: the durable identifiers and the
    attestation that ``PromotionGateClient`` had just VALIDATED were dropped on the way out, so
    the caller received a report that could not be traced back to the run that produced it. The
    two classes are now the same object and only the ``dataset`` label is replaced.
    """
    respx.post(f"{_BASE}/v1/evaluations").mock(return_value=httpx.Response(200, json=_eval_body()))

    report = _adapter().evaluate(_DATASET_PATH)

    assert report.run_id == "run-fictional-0001"
    assert report.dataset_digest == "sha256:feedfacefeedfacefeedfacefeedfacefeedface"
    assert report.evaluator == "hrz4-quality.example"
    assert report.artifact_refs == ("gs://fictional-hrz4-evidence/run-fictional-0001/report.json",)
    assert report.attested is True
    assert report.dataset_version == "v1"
    assert report.schema_version == "eval-run/v1"
    # The deliberate relabelling is the ONLY difference from what the client returned.
    assert report.dataset == _DATASET_ID


@respx.mock
def test_evaluate_refuses_thin_evidence_without_examples_or_run_identity() -> None:
    """The client fails closed: a results list alone is not evaluation evidence."""
    thin = {
        "results": [
            {"metric": "plan_groundedness", "score": 0.91, "threshold": 0.80, "passed": True}
        ]
    }
    respx.post(f"{_BASE}/v1/evaluations").mock(return_value=httpx.Response(200, json=thin))
    with pytest.raises(RemoteEvaluationError):
        _adapter().evaluate(_DATASET_PATH)


@respx.mock
def test_gate_posts_to_v1_gate_and_returns_bool() -> None:
    route = respx.post(f"{_BASE}/v1/gate").mock(
        return_value=httpx.Response(200, json=_gate_body(eval_passed=True))
    )

    passed = _adapter().gate(_DATASET_PATH)

    assert passed is True
    assert route.called
    # It is a POST (not a GET) and carries the same structured body + bundle selection.
    request = route.calls.last.request
    assert request.method == "POST"
    sent = json.loads(request.content)
    assert sent["bundle"] == "mkt2-campaign"
    assert sent["dataset_id"] == sent["target"]["dataset_id"] == _DATASET_ID
    assert "metrics" not in sent


@respx.mock
def test_gate_returns_false_when_hrz4_declines_with_consistent_evidence() -> None:
    """A FAIL must be reached through consistent evidence: one metric row genuinely failing."""
    respx.post(f"{_BASE}/v1/gate").mock(
        return_value=httpx.Response(200, json=_gate_body(eval_passed=False))
    )
    assert _adapter().gate(_DATASET_PATH) is False


@respx.mock
def test_gate_refuses_a_naked_aggregate_boolean() -> None:
    """The unhardened ``{"passed": true}`` shape is rejected, not trusted."""
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json={"passed": True}))
    with pytest.raises(RemoteEvaluationError):
        _adapter().gate(_DATASET_PATH)


@respx.mock
def test_gate_refuses_an_aggregate_that_contradicts_its_evidence() -> None:
    """``passed: true`` over a failing metric row is an inconsistency, never a promotion."""
    body = _gate_body(eval_passed=False)
    body["passed"] = True  # contradicts the failing citation_accuracy row
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(RemoteEvaluationError):
        _adapter().gate(_DATASET_PATH)


@respx.mock
def test_non_2xx_raises_remote_evaluation_error() -> None:
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(422, text="unknown metric name")
    )
    with pytest.raises(RemoteEvaluationError):
        _adapter().evaluate(_DATASET_PATH)
