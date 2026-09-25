"""What the console's model pill states first must be true of the profile the service runs.

Every served console shows two small pills at the top right (owner decision, 2026-09-23): the
model that answered, and ``Search`` when an online search tool was used. Until the first answer
arrives the model pill states ``generator_model`` from ``/healthz``, dimmed, with WHERE the
runtime sits (``runtime``) in its title. Both come from the service because the browser cannot
know either. After an answer, the pill states the response's ``X-Answered-By``; that half is held
in ``test_answer_provenance.py``.

The reason this is worth a test rather than a glance: these systems are demonstrated on a laptop
and on a deployment, sometimes in the same hour, and a pill that was present but wrong is worse
than none. So the assertions below are about AGREEMENT with the profile, not about presence.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from campaign_planner.config import Settings

CONFIG_PATH = Path("config/settings.yaml")

#: Answers that mean "no managed model produced this". Each says something different and the
#: difference is the point, which is why this is a set rather than one sentinel:
#: ``deterministic-offline-stub`` says a model-shaped port is bound to a stub;
#: ``no-model`` says there is no such port at all; ``onprem-not-implemented`` says the port
#: exists and refuses. A reviewer approving an escalation is entitled to know which they read.
_NON_MANAGED_ANSWERS = frozenset(
    {
        "deterministic-offline-stub",
        "no-model",
        "onprem-not-implemented",
        "managed-model-unavailable",
    }
)


def _for_profile(profile: str) -> Settings:
    return dataclasses.replace(Settings.load(CONFIG_PATH), profile=profile)


@pytest.mark.parametrize("profile", ["local", "gcp", "onprem"])
def test_the_runtime_half_states_where_the_process_runs(profile: str) -> None:
    """``onprem`` reads ``local``, because that is its entire point.

    A managed model call does not make a process cloud-hosted. This half is about where the
    PROCESS runs and the other half is about whose model answers, and collapsing the two is how
    an on-premises deployment ends up describing itself as running on GCP.
    """
    settings = _for_profile(profile)
    assert settings.runtime == ("gcp" if profile == "gcp" else "local")


@pytest.mark.parametrize("profile", ["local", "gcp", "onprem"])
def test_the_model_half_is_always_answered(profile: str) -> None:
    """A blank is not an option: the pill renders nothing rather than render a falsehood."""
    assert _for_profile(profile).generator_model.strip()


@pytest.mark.parametrize("profile", ["local", "onprem"])
def test_no_offline_profile_claims_a_managed_model(profile: str) -> None:
    """The defect that matters, stated as an assertion.

    A laptop run naming a Gemini model is precisely the confusion the pill exists to remove,
    and it is the one direction a reviewer cannot detect by looking at the page.
    """
    answer = _for_profile(profile).generator_model
    assert answer in _NON_MANAGED_ANSWERS, (
        f"the {profile!r} profile reports {answer!r}, which reads as a managed model answering "
        "a request that never left the machine"
    )


def test_the_health_contract_carries_both_halves() -> None:
    """The wire contract the console actually reads. A property nothing serves is not a contract.

    Asserted on the response MODEL rather than by calling ``/healthz`` through a test client.
    That is not a convenience: under the ``local`` posture these services deliberately refuse an
    unauthenticated non-loopback peer, so a client call here would exercise that refusal instead
    of this contract, and the refusal already has its own tests. What must not rot is that the
    two fields exist on the response the endpoint returns.
    """
    from campaign_planner.api.schemas import HealthModel

    fields = set(HealthModel.model_fields)
    assert "runtime" in fields, "the console reads runtime off /healthz and the field is absent"
    assert "generator_model" in fields


def test_the_endpoint_answers_from_settings_rather_than_a_literal() -> None:
    """A pill value hard-coded at the endpoint would be right once and wrong after the next rebind.

    Both halves are properties of :class:`Settings`, so the values the endpoint sends are the
    values the profile implies; this pins that they are readable and non-empty together, which
    is what the endpoint relies on.
    """
    settings = Settings.load(CONFIG_PATH)
    assert settings.runtime in {"gcp", "local"}
    assert settings.generator_model.strip()


def test_the_managed_profile_names_a_model_or_says_exactly_why_not() -> None:
    """No placeholder survives here: every answer is a model id or a stated reason.

    ``managed-model-unnamed`` used to be a real answer in twenty-five trees, and it was the
    resolver looking in the wrong place rather than the trees being silent -- most of the fleet
    pins the id in settings under a per-repository field name. It is kept only as a defensive
    fallback and no tree should reach it.
    """
    answer = _for_profile("gcp").generator_model
    assert answer != "managed-model-unnamed", (
        "the managed model id is not being resolved from anywhere: set _GENERATOR_MODEL_ATTR "
        "to the settings path holding it, or declare _MODEL on the bound adapter"
    )
    assert answer.strip()


def test_not_implemented_is_claimed_only_by_an_adapter_that_never_calls_a_model() -> None:
    """The one answer that is INFERRED rather than read, so it is the one that can be wrong.

    ``managed-not-implemented`` is reached when a tree names no settings path and its adapter
    declares no model constant. That is correct for a deployment-wired placeholder, and a LIE
    for an adapter that generates while declaring nothing.

    The check is "does it call the model API", not "does it raise". Raising was tried first and
    is too weak: it passed `soc-fraud-fusion`, which generates and also raises on bad input, and
    it had already let a real mis-classification through -- `conversation-qa-scorecard` calls
    ``generate_content`` and raises only when its model is unconfigured, and was grouped with
    the placeholders on the strength of that raise. Its model is named now.
    """
    from importlib import import_module
    from pathlib import Path as _Path

    # The MANAGED profile, not whatever the settings file defaults to. Reading the default
    # profile here made this test inert: offline it answers `deterministic-offline-stub`, so it
    # returned before checking anything, and it passed a deliberately broken tree.
    settings = _for_profile("gcp")
    if settings.generator_model != "managed-not-implemented":
        return
    from campaign_planner.config import _GENERATOR_PORT

    binding = str((settings.adapters.get(_GENERATOR_PORT) or {}).get("gcp", ""))
    module = import_module(binding.partition(":")[0])
    source = _Path(module.__file__ or "").read_text()
    for call in ("generate_content", ".predict(", ".invoke("):
        assert call not in source, (
            f"{binding} reports managed-not-implemented but calls {call!r}: it generates, so "
            "the model it calls must be named rather than declared absent"
        )


def _code_only(source: str) -> str:
    """``source`` with ``//`` line comments and ``/* */`` blocks removed, so prose cannot pass."""
    import re as _re

    return _re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=_re.S)


def test_the_pills_call_the_base_this_console_actually_serves() -> None:
    """The half of the contract that lives in the BROWSER, and the half that was once broken.

    The old banner fetched ``/api/agent/healthz``, the same-origin route handler the service
    template ships. This console has none; it calls its backend directly on
    ``NEXT_PUBLIC_API_BASE``. So the health call reached nothing and the banner rendered nothing,
    on every page load, with every service-side assertion above green. The pills keep the rule:
    a tree with ``ui/app/api/agent`` reads that path; a tree without one reads the same base the
    rest of its console reads, for health and for the answers alike.
    """
    pills = _code_only(Path("ui/app/ModelPills.tsx").read_text())
    proxies_through_own_origin = Path("ui/app/api/agent").is_dir()
    assert ('"/api/agent"' in pills) == proxies_through_own_origin
    if not proxies_through_own_origin:
        assert "`${API_BASE}/healthz`" in pills, "health must use the console's own API base"
        assert "watchAnswers(window, API_BASE," in pills, (
            "the answers must be read off the same base the console calls, or a pill never moves"
        )


def test_the_console_shows_the_model_that_answered_as_pills_not_a_banner() -> None:
    """Two pills name the model that ANSWERED, and Search when it searched.

    The whole chain, held from the offline gate: the pills start from ``/healthz`` with
    ``generator_model`` and ``runtime``, read both answer headers through the one fetch wrapper,
    are mounted in the layout, and the service emits both headers (the kit middleware, which also
    exposes them to this cross-origin console; ``test_answer_provenance.py`` proves that on the
    wire). A service that never installed it would leave the pills on the configured model
    forever with every node test green.
    ``ui/tests/answer-provenance.test.mjs`` proves the wrapper itself.
    """
    pills = _code_only(Path("ui/app/ModelPills.tsx").read_text())
    assert "generator_model" in pills and "runtime" in pills
    assert "running on GCP" in pills and "running locally" in pills
    assert "answered the last request" in pills
    watcher = Path("ui/lib/answer-provenance.mjs").read_text()
    for header in ('"x-answered-by"', '"x-search-used"'):
        assert header in watcher, "the pills never read " + header
    layout = Path("ui/app/layout.tsx").read_text()
    assert "<ModelPills />" in layout, "the pills are not mounted on every page"
    service = Path("src/campaign_planner/api/app.py").read_text()
    assert "install_answer_provenance(app)" in service
    assert not Path("ui/app/ProvenanceBanner.tsx").exists(), "the old banner is back"
    assert Path("ui/tests/answer-provenance.test.mjs").exists()


def _rule(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start : css.index("}", start)]


def test_the_pills_are_pinned_where_a_reader_can_see_them() -> None:
    """A strip that rendered off-screen once satisfied every other assertion in this file.

    The old banner's ``margin: -32px`` was carried from a padded-``body`` console into this one,
    whose ``body`` has no padding, and hoisted the strip 32px above the viewport: in the DOM on
    every page load, visible on none. The pills are fixed to the viewport's top right instead,
    so no page geometry can push them out of view, and the old rule must not come back.
    """
    css = Path("ui/app/globals.css").read_text()
    assert ".provenance-banner" not in css
    rule = _rule(css, ".model-pills")
    assert "position: fixed;" in rule
    for anchor in ("top:", "right:"):
        assert anchor in rule, "the pills are not anchored to the top right"
