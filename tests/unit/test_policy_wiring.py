from types import SimpleNamespace

import pytest

from campaign_planner.api.deps import make_audience_selection_service, make_plan_service
from campaign_planner.config import PolicySettings


def test_adopter_policy_overrides_are_wired_into_deterministic_engines() -> None:
    marker = object()
    container = SimpleNamespace(
        settings=SimpleNamespace(
            policy=PolicySettings(
                audience_propensity_weight=2.0,
                allocation_saturation_frequency=4.0,
                reach_effective_factor=0.5,
                pacing_ramp_low=0.25,
                pacing_ramp_high=1.75,
            )
        ),
        audience=marker,
        llm=marker,
        guardrail=marker,
        tracer=marker,
        audit=marker,
        review_router=None,
    )
    service = make_plan_service(container)
    assert service._selection.propensity_weight == 2.0
    assert service._allocation.saturation_frequency == 4.0
    assert service._reach.effective_reach_factor == 0.5
    assert service._pacing.ramp_high == 1.75
    assert make_audience_selection_service(container).propensity_weight == 2.0


@pytest.mark.parametrize("field", ["audience_propensity_weight", "audience_value_weight"])
def test_negative_ranking_weights_are_refused(field: str) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        PolicySettings(**{field: -0.01})
