"""LlmPort — LLM text/reasoning for drafting the creative brief and the plan summary.

Primary GCP adapter: Gemini models on the Gemini Enterprise Agent Platform
(``gemini-3.5-flash`` for drafting, ``gemini-3.1-flash-lite`` for triage). The LLM only
drafts the creative brief and narrates the plan summary over the already-computed
deterministic plan; it never decides the audience, the budget split, the reach numbers or
the pacing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import LlmRequest, LlmResponse


@runtime_checkable
class LlmPort(Protocol):
    def generate(self, request: LlmRequest) -> LlmResponse:
        """Generate a completion for ``request`` using the configured model."""
        ...

    def classify(self, text: str, labels: list[str]) -> str:
        """Cheap single-label classification (triage/routing tier model)."""
        ...
