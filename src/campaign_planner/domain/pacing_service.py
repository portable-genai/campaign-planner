"""PacingService — deterministic pacing / calendar (flight-schedule) builder.

The fourth deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given a flight window, a number of legs, a total budget and a
pacing strategy, it splits the window into equal-length legs and distributes the budget by
a transparent weight curve (even / front-loaded / back-loaded). How spend is paced across
the calendar is consequential (it governs daily burn and platform delivery), so it is code,
not an LLM call.

Determinism: same inputs -> same output. ``as_of`` is never read from a clock; the window is
passed in. The weight curves are explicit and the per-leg amounts always sum back to the
total budget (the last leg absorbs any rounding remainder), so the calendar reconciles
exactly. The leg boundaries are computed by integer day arithmetic on the standard library
``date`` type only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .errors import InvalidFlightError
from .models import (
    FlightLeg,
    FlightSchedule,
    Market,
    PacingStrategy,
    Vertical,
)


@dataclass(frozen=True, slots=True)
class PacingService:
    """Pure, deterministic flight-schedule builder with explicit weight curves."""

    # Front/back-loaded curves use a linear ramp between these bounds (tunable).
    ramp_low: float = 0.5
    ramp_high: float = 1.5

    def build(
        self,
        start_date: date,
        end_date: date,
        legs: int,
        total_budget: float,
        strategy: PacingStrategy,
        market: Market,
        vertical: Vertical,
    ) -> FlightSchedule:
        if end_date < start_date:
            raise InvalidFlightError(
                f"end_date {end_date.isoformat()} is before start_date {start_date.isoformat()}"
            )
        if legs < 1:
            raise InvalidFlightError(f"legs must be >= 1, got {legs}")

        # A flight cannot have more legs than it has days: each leg needs at least one day,
        # otherwise legs would spill past the requested end_date and the final leg would get
        # an inverted (end before start) date range. Cap legs at the window length in days.
        total_days = (end_date - start_date).days + 1
        legs = min(legs, total_days)

        boundaries = self._leg_boundaries(start_date, end_date, legs)
        weights = self._weights(legs, strategy)
        amounts = self._amounts(total_budget, weights)

        built: list[FlightLeg] = []
        for i, ((leg_start, leg_end), weight, amount) in enumerate(
            zip(boundaries, weights, amounts, strict=True)
        ):
            built.append(
                FlightLeg(
                    index=i,
                    start_date=leg_start.isoformat(),
                    end_date=leg_end.isoformat(),
                    weight=round(weight, 4),
                    amount=amount,
                )
            )
        return FlightSchedule(
            market=market,
            vertical=vertical,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            strategy=strategy,
            total_budget=round(total_budget, 2),
            legs=tuple(built),
        )

    # ------------------------------------------------------------------ #
    # Leg boundaries
    # ------------------------------------------------------------------ #
    @staticmethod
    def _leg_boundaries(start_date: date, end_date: date, legs: int) -> list[tuple[date, date]]:
        """Split the inclusive window into ``legs`` contiguous, near-equal day ranges."""
        total_days = (end_date - start_date).days + 1
        base = total_days // legs
        extra = total_days % legs  # spread the remainder across the first legs
        boundaries: list[tuple[date, date]] = []
        cursor = start_date
        for i in range(legs):
            length = base + (1 if i < extra else 0)
            length = max(length, 1)
            leg_end = cursor + timedelta(days=length - 1)
            if i == legs - 1:
                leg_end = end_date
            boundaries.append((cursor, leg_end))
            cursor = leg_end + timedelta(days=1)
        return boundaries

    # ------------------------------------------------------------------ #
    # Weight curves
    # ------------------------------------------------------------------ #
    def _weights(self, legs: int, strategy: PacingStrategy) -> list[float]:
        if strategy is PacingStrategy.EVEN or legs == 1:
            raw = [1.0] * legs
        elif strategy is PacingStrategy.FRONT_LOADED:
            raw = self._ramp(legs, high_first=True)
        else:  # BACK_LOADED
            raw = self._ramp(legs, high_first=False)
        total = sum(raw)
        return [w / total for w in raw]

    def _ramp(self, legs: int, high_first: bool) -> list[float]:
        steps = [
            self.ramp_high - (self.ramp_high - self.ramp_low) * (i / (legs - 1))
            for i in range(legs)
        ]
        return steps if high_first else list(reversed(steps))

    # ------------------------------------------------------------------ #
    # Amounts (sum reconciles exactly to the total budget)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _amounts(total_budget: float, weights: list[float]) -> list[float]:
        amounts = [round(total_budget * w, 2) for w in weights]
        # The last leg absorbs the rounding remainder so the legs sum to the total exactly.
        drift = round(total_budget - sum(amounts), 2)
        if amounts:
            amounts[-1] = round(amounts[-1] + drift, 2)
        return amounts
