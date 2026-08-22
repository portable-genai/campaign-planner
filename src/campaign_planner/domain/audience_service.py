"""AudienceSelectionService — deterministic audience / segment selection.

The first deterministic engine in the D2 pipeline (see the ``deterministic-domain-service``
skill): pure, stdlib-only, replayable. Given the candidate audience segments returned by
the audience-data port, it ranks and selects the segments to target by a transparent score
that combines modelled propensity, per-conversion expected value, and marketing-consent
rate, then keeps the top-N. Which audience a campaign spends against is consequential and
auditable, so it is code, not an LLM call.

Determinism: same inputs -> same output. No LLM, no clock, no network, no randomness. The
weights and the consent floor are tunable fields, not magic numbers. Segments with no
consented, reachable audience are dropped (a campaign may not target people who did not
consent), so the selection respects PDPA / APP / consent rules generically.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AudienceSegment, Citation, SelectedSegment


@dataclass(frozen=True, slots=True)
class AudienceSelectionService:
    """Pure, deterministic segment ranking and selection.

    The score is ``propensity^p x normalised_value^v x consent_rate``, all in 0..1, so a
    high-propensity, high-value, fully-consented segment scores near 1.0. ``min_consent``
    drops segments below a consent floor; ``max_segments`` caps the selection.
    """

    propensity_weight: float = 1.0
    value_weight: float = 0.5
    min_consent: float = 0.0
    min_reachable: int = 1

    def select(
        self,
        segments: tuple[AudienceSegment, ...] | list[AudienceSegment],
        max_segments: int = 5,
    ) -> tuple[SelectedSegment, ...]:
        """Rank consented, reachable segments and return the top ``max_segments``."""
        eligible = [
            s
            for s in segments
            if s.consent_rate >= self.min_consent and s.consented_reachable >= self.min_reachable
        ]
        if not eligible:
            return ()
        max_value = max((s.expected_value for s in eligible), default=0.0) or 1.0

        scored: list[tuple[float, AudienceSegment]] = []
        for s in eligible:
            scored.append((self._score(s, max_value), s))

        # Sort by score desc, then by consented-reachable desc, then id for stability.
        scored.sort(key=lambda pair: (-pair[0], -pair[1].consented_reachable, pair[1].id))

        out: list[SelectedSegment] = []
        for rank, (score, segment) in enumerate(scored[: max(max_segments, 1)], start=1):
            out.append(
                SelectedSegment(
                    segment=segment,
                    score=round(score, 4),
                    rank=rank,
                    rationale=self._rationale(segment, score, max_value),
                    citations=self._citations(segment),
                )
            )
        return tuple(out)

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #
    def _score(self, segment: AudienceSegment, max_value: float) -> float:
        propensity = max(0.0, min(segment.propensity, 1.0))
        norm_value = max(0.0, min(segment.expected_value / max_value, 1.0)) if max_value else 0.0
        consent = max(0.0, min(segment.consent_rate, 1.0))
        prop_term = propensity**self.propensity_weight
        value_term = norm_value**self.value_weight
        return prop_term * value_term * consent

    @staticmethod
    def _rationale(segment: AudienceSegment, score: float, max_value: float) -> str:
        return (
            f"propensity {segment.propensity:.2f}, value {segment.expected_value:.0f}, "
            f"consent {segment.consent_rate:.2f}, consented-reachable "
            f"{segment.consented_reachable} -> score {score:.2f}"
        )

    @staticmethod
    def _citations(segment: AudienceSegment) -> tuple[Citation, ...]:
        return segment.citations
