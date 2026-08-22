"""ReachFrequencyService — deterministic reach / frequency estimation.

The third deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given the allocated channel mix and the consented, addressable
audience ceiling, it estimates total impressions, de-duplicated unique reach, average
frequency, and effective reach (people seeing the campaign at or above the effective-
frequency threshold, the classic "3+" rule). Reach / frequency drives whether a plan can
actually achieve its objective, so it is auditable code, not an LLM estimate.

Determinism: same inputs -> same output. No LLM, no clock, no randomness, no network. The
audience-overlap factor and the effective-frequency threshold are tunable fields. The model
is a transparent, documented one (cross-channel reach via the standard independence /
"one minus the product of non-reach" combination), so an auditor can re-derive every figure.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ChannelMix, Citation, Market, ReachFrequency, Vertical


@dataclass(frozen=True, slots=True)
class ReachFrequencyService:
    """Pure, deterministic reach / frequency / effective-reach estimation."""

    # Fraction of the at-frequency audience that reaches the effective-frequency threshold.
    # A transparent attenuation of unique reach as frequency rises (documented, tunable).
    effective_reach_factor: float = 0.7

    def estimate(
        self,
        channel_mix: ChannelMix,
        addressable: int,
        market: Market,
        vertical: Vertical,
        effective_frequency: int = 3,
    ) -> ReachFrequency:
        impressions = sum(line.expected_impressions for line in channel_mix.lines)
        unique_reach = self._combined_unique_reach(channel_mix, addressable)
        average_frequency = round(impressions / unique_reach, 2) if unique_reach > 0 else 0.0
        effective_reach = self._effective_reach(
            unique_reach, average_frequency, effective_frequency
        )
        rationale = (
            f"{impressions} impression(s) across {len(channel_mix.lines)} channel(s); "
            f"{unique_reach} unique people reached of {addressable} addressable "
            f"({(unique_reach / addressable * 100) if addressable else 0:.1f}%); "
            f"avg frequency {average_frequency:.2f}; "
            f"{effective_reach} at {effective_frequency}+ effective frequency."
        )
        return ReachFrequency(
            market=market,
            vertical=vertical,
            impressions=impressions,
            unique_reach=unique_reach,
            addressable=addressable,
            average_frequency=average_frequency,
            effective_reach=effective_reach,
            effective_frequency=effective_frequency,
            rationale=rationale,
            citations=self._citations(channel_mix),
        )

    # ------------------------------------------------------------------ #
    # Reach math
    # ------------------------------------------------------------------ #
    @staticmethod
    def _combined_unique_reach(channel_mix: ChannelMix, addressable: int) -> int:
        """De-duplicate per-channel reach via the standard independence combination.

        Combined reach = addressable * (1 - prod(1 - per_channel_reach / addressable)).
        This treats audiences as independently sampled, the conventional planning model,
        and caps at the addressable ceiling. With one channel it reduces to that channel's
        reach; with several it is always below the naive sum (overlap removed).
        """
        if addressable <= 0:
            return 0
        non_reach = 1.0
        for line in channel_mix.lines:
            p = min(line.expected_reach / addressable, 1.0)
            non_reach *= 1.0 - p
        combined = addressable * (1.0 - non_reach)
        return min(int(round(combined)), addressable)

    def _effective_reach(
        self, unique_reach: int, average_frequency: float, effective_frequency: int
    ) -> int:
        """People at or above the effective frequency, as a transparent attenuation.

        If average frequency already meets the threshold, the bulk of unique reach is
        effective (scaled by ``effective_reach_factor``); below it, effective reach scales
        down proportionally to how close average frequency is to the threshold.
        """
        if unique_reach <= 0 or effective_frequency <= 0:
            return 0
        ratio = min(average_frequency / effective_frequency, 1.0)
        return int(round(unique_reach * self.effective_reach_factor * ratio))

    @staticmethod
    def _citations(channel_mix: ChannelMix) -> tuple[Citation, ...]:
        out: list[Citation] = []
        seen: set[tuple[str, int | None]] = set()
        for line in channel_mix.lines:
            for c in line.citations:
                key = (c.source_id, c.page)
                if key not in seen:
                    seen.add(key)
                    out.append(c)
        return tuple(out)
