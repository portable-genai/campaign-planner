"""BudgetAllocationService — deterministic channel-mix and budget optimiser.

The second, central deterministic engine (see the ``deterministic-domain-service`` skill):
pure, stdlib-only, replayable. Given a total budget and the per-channel cost / performance
benchmarks, it allocates spend across channels to maximise expected conversions subject to
each channel's reach ceiling and minimum-spend floor. This is the spend-affecting decision
at the heart of D2, so it is transparent code an auditor can re-run and a test can pin, not
an LLM guess. The LLM only narrates the resulting mix afterwards.

Algorithm (efficiency-greedy with reach-saturation and floors, fully deterministic):

1. Reserve each channel's ``min_spend`` floor (so contractual minima are honoured).
2. Rank channels by efficiency (lowest deterministic cost-per-conversion first).
3. Pour the remaining budget into channels in efficiency order up to each channel's
   reach-saturation spend (the spend at which unique reach hits ``max_reach`` at the
   assumed frequency), so the most efficient unique reach is bought first.
4. Any budget left after every channel is saturated is distributed across the channels in
   efficiency order (frequency rises beyond saturation rather than leaving spend on the
   table, as real media plans do), with the last channel absorbing the rounding remainder.
   The full budget is therefore always allocated and reconciles exactly; unique reach per
   channel is still capped at ``max_reach`` in the line math.

Determinism: same inputs -> same output. No LLM, no clock, no randomness, no network.
Weights / step granularity are fields, not magic numbers; ties break on the channel name.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidBudgetError, NoChannelBenchmarkError
from .models import (
    BudgetLine,
    Channel,
    ChannelBenchmark,
    ChannelMix,
    Citation,
    Market,
    Vertical,
)


@dataclass(frozen=True, slots=True)
class _Cap:
    """The spend ceiling and conversion math for one channel, precomputed."""

    benchmark: ChannelBenchmark
    impressions_per_currency: float  # impressions bought per unit of currency
    max_spend: float  # spend that saturates max_reach (frequency-capped)


@dataclass(frozen=True, slots=True)
class BudgetAllocationService:
    """Pure, deterministic budget allocation across channels (efficiency-greedy)."""

    # Assumed average frequency used to convert reach ceiling into an impression ceiling.
    saturation_frequency: float = 3.0
    # Smallest tolerated leftover before it is reported as unallocated.
    epsilon: float = 0.01

    def allocate(
        self,
        total_budget: float,
        benchmarks: tuple[ChannelBenchmark, ...] | list[ChannelBenchmark],
        market: Market,
        vertical: Vertical,
        channels: tuple[Channel, ...] = (),
    ) -> ChannelMix:
        if total_budget <= 0:
            raise InvalidBudgetError(f"total_budget must be positive, got {total_budget}")
        selected = self._filter_benchmarks(benchmarks, channels)
        if not selected:
            raise NoChannelBenchmarkError(
                f"no channel benchmarks for {market.value}/{vertical.value}"
            )

        caps = [self._cap(b) for b in selected]
        floors_total = sum(c.benchmark.min_spend for c in caps)
        if floors_total > total_budget + self.epsilon:
            raise InvalidBudgetError(
                f"channel minimum spends ({floors_total:.2f}) exceed total budget "
                f"({total_budget:.2f}) for {market.value}/{vertical.value}"
            )

        spend = self._greedy_fill(total_budget, caps)
        lines = tuple(
            self._line(cap, spend[cap.benchmark.channel], total_budget)
            for cap in self._order(caps)
            if spend[cap.benchmark.channel] > 0
        )
        return ChannelMix(
            market=market,
            vertical=vertical,
            total_budget=round(total_budget, 2),
            lines=lines,
        )

    # ------------------------------------------------------------------ #
    # Allocation core
    # ------------------------------------------------------------------ #
    def _greedy_fill(self, total_budget: float, caps: list[_Cap]) -> dict[Channel, float]:
        ordered = self._order(caps)
        spend: dict[Channel, float] = {c.benchmark.channel: 0.0 for c in caps}
        remaining = total_budget

        # 1. Honour the minimum-spend floors first.
        for cap in ordered:
            floor = cap.benchmark.min_spend
            if floor > 0:
                spend[cap.benchmark.channel] = floor
                remaining -= floor

        # 2. Pour the rest into channels by efficiency, up to each reach-saturation spend.
        for cap in ordered:
            if remaining <= self.epsilon:
                break
            headroom = max(0.0, cap.max_spend - spend[cap.benchmark.channel])
            add = min(headroom, remaining)
            if add > 0:
                spend[cap.benchmark.channel] += add
                remaining -= add

        # 3. Distribute any saturated-out remainder across channels weighted by reach
        #    capacity so the full budget is always allocated (frequency rises beyond
        #    saturation on the largest-reach channels first; per-channel reach stays capped).
        if remaining > self.epsilon and ordered:
            reach_total = sum(c.benchmark.max_reach for c in ordered)
            for cap in ordered:
                weight = (
                    cap.benchmark.max_reach / reach_total if reach_total > 0 else 1.0 / len(ordered)
                )
                spend[cap.benchmark.channel] += remaining * weight

        rounded = {ch: round(v, 2) for ch, v in spend.items()}
        # The last channel in efficiency order absorbs any rounding drift for exact reconciliation.
        drift = round(total_budget - sum(rounded.values()), 2)
        if abs(drift) >= 0.01 and ordered:
            last = ordered[-1].benchmark.channel
            rounded[last] = round(rounded[last] + drift, 2)
        return rounded

    @staticmethod
    def _order(caps: list[_Cap]) -> list[_Cap]:
        """Efficiency order: lowest cost-per-conversion first, then channel name (stable)."""
        return sorted(
            caps,
            key=lambda c: (c.benchmark.cost_per_conversion, c.benchmark.channel.value),
        )

    # ------------------------------------------------------------------ #
    # Per-channel math
    # ------------------------------------------------------------------ #
    def _cap(self, benchmark: ChannelBenchmark) -> _Cap:
        impressions_per_currency = 1000.0 / benchmark.cpm if benchmark.cpm > 0 else 0.0
        # Saturate when unique reach hits max_reach at the assumed frequency.
        saturating_impressions = benchmark.max_reach * self.saturation_frequency
        max_spend = (
            saturating_impressions / impressions_per_currency
            if impressions_per_currency > 0
            else 0.0
        )
        return _Cap(
            benchmark=benchmark,
            impressions_per_currency=impressions_per_currency,
            max_spend=round(max_spend, 2),
        )

    def _line(self, cap: _Cap, amount: float, total_budget: float) -> BudgetLine:
        b = cap.benchmark
        impressions = int(round(amount * cap.impressions_per_currency))
        # Unique reach is impressions de-duplicated at the assumed frequency, capped.
        reach = min(int(round(impressions / self.saturation_frequency)), b.max_reach)
        conversions = round(impressions * b.ctr * b.conversion_rate, 2)
        cpc = round(amount / conversions, 2) if conversions > 0 else float("inf")
        return BudgetLine(
            channel=b.channel,
            amount=round(amount, 2),
            share=round(amount / total_budget, 4) if total_budget > 0 else 0.0,
            expected_impressions=impressions,
            expected_reach=reach,
            expected_conversions=conversions,
            expected_cost_per_conversion=cpc,
            citations=self._citations(b),
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _filter_benchmarks(
        benchmarks: tuple[ChannelBenchmark, ...] | list[ChannelBenchmark],
        channels: tuple[Channel, ...],
    ) -> list[ChannelBenchmark]:
        if not channels:
            return list(benchmarks)
        wanted = set(channels)
        return [b for b in benchmarks if b.channel in wanted]

    @staticmethod
    def _citations(benchmark: ChannelBenchmark) -> tuple[Citation, ...]:
        return benchmark.citations
