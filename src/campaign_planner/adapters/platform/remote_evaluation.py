"""Remote-platform evaluation adapter : thin HTTP client to Hrz4.

At promotion this vertical's quality is checked against the shared **Hrz4 AI Quality /
model-risk** service (``model-quality-gate``). This adapter implements
:class:`EvaluationGatePort` against Hrz4's hardened contract:

* ``evaluate`` -> ``POST /v1/evaluations {target, dataset_id, bundle}`` -> EvalReport.
* ``gate``     -> ``POST /v1/gate {target, dataset_id, bundle}`` -> ``{passed}``.

**Sourced from the shared ``agent-eval-kit`` commons.** The HTTP contract
is ``agent_eval_kit.gate_client.PromotionGateClient``; this adapter configures it (the
registered ``mkt2-campaign`` bundle, the reasoning model, and this repo's S2S auth
headers), relabels its report with the dataset_id, and re-raises its errors as
:class:`RemoteEvaluationError`.

There is no longer a domain-vs-package report mapping here, and its removal is the point. The
domain ``EvalReport`` was a hand-copied three-field subset, so ``_to_domain`` rebuilt one field by
field and silently dropped exactly the evidence the client had just validated: the
``run_id``, the ``dataset_digest``, the ``evaluator``, the ``artifact_refs`` and the ``attested``
flag. Both names are now the SAME class, so the report is passed through and only its ``dataset``
label is replaced.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePath

from agent_eval_kit.gate_client import GateClientError, PromotionGateClient

from ...config import Settings
from ...domain.errors import CampaignPlanError
from ...domain.models import EvalReport
from ...envread import setting_or_default
from . import _s2s

_DEFAULT_URL = "http://localhost:8084"

#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + bars).
_BUNDLE = "mkt2-campaign"
#: Prompt/agent version tag; bump when the prompt corpus changes, or source it from a registry.
_PROMPT_VERSION = "v1"


class RemoteEvaluationError(CampaignPlanError):
    """Raised when the Hrz4 quality service returns a non-2xx response."""


class RemoteEvaluationAdapter:
    """HTTP client for the Hrz4 ``model-quality-gate`` service (via PromotionGateClient)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = PromotionGateClient(
            setting_or_default("QUALITY_GATE_URL", _DEFAULT_URL),
            bundle=_BUNDLE,
            model=settings.models.reasoning,
            prompt_version=_PROMPT_VERSION,
            auth_headers=lambda: _s2s.headers(),
        )

    def evaluate(self, dataset_path: str) -> EvalReport:
        """Score ``dataset_path`` via Hrz4 and return its report, relabelled with the dataset_id."""
        try:
            report = self._client.evaluate(dataset_path)
        except GateClientError as exc:
            raise RemoteEvaluationError(str(exc)) from exc
        # The report is labelled with the dataset_id (basename, no .jsonl), the same identifier
        # the wire contract carries. ``replace`` rather than a rebuild: every other field,
        # including the attested evidence the client validated, survives untouched.
        return replace(report, dataset=PurePath(dataset_path).name.removesuffix(".jsonl"))

    def gate(self, target: str) -> bool:
        """Promotion gate: True iff Hrz4 reports ``target`` passes."""
        try:
            return self._client.gate(target)
        except GateClientError as exc:
            raise RemoteEvaluationError(str(exc)) from exc
