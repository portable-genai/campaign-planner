"""F2: the presenter demo is driven through a real headless browser, not a string.

``scripts/demo_selftest.py`` starts the real server and reads the served bytes, which
covers the server/renderer path browserlessly. This file closes the other half: a pinned
headless Chromium loads the SERVED pages, clicks the presenter's own ``Next`` button, and
reads every asserted figure back out of the LIVE DOM through the stable ``data-*``
evidence hooks. Nothing here is compared against hard-coded prose; every expectation is
recomputed from the running :class:`DemoSession`.

``scripts/demo_playwright.py`` is the presenter's narrated walkthrough of the same server
and shares its selectors; this file is the gated assertion of the live figures.

Playwright is pinned in the ``[demo]`` extra and the browser binary is a network download,
so a fork's day-one offline gate must not depend on either: with nothing set, an absent
extra or an unlaunchable browser still skips LOUDLY (``-rs``, as ``make demo-browser`` runs
it) rather than passing silently. That default is a courtesy to a clean checkout, not a
licence. Set ``DEMO_BROWSER_REQUIRED`` and the same conditions FAIL instead, because a suite
that declines to run reports exactly the green a suite that ran reports, and a runner that
installed a browser on purpose is the one place that must never be handed a skip.
``CHROME_PATH`` names the binary to drive, the same read ``scripts/demo_playwright.py``
makes, so a runner carrying its own chromium is driven rather than quietly ignored.
"""

from __future__ import annotations

import importlib
import os
import sys
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, NoReturn

import pytest

from campaign_planner.envread import boolean_setting

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

#: Which local Chrome or Chromium binary Playwright drives, the same read
#: ``scripts/demo_playwright.py`` makes. Unset means Playwright's own pinned download, because
#: ``executable_path=None`` is Playwright's own default, so honouring the variable changes
#: nothing for anyone who leaves it alone. It was NOT honoured here before, and a runner that
#: ships a distribution chromium and exports ``CHROME_PATH`` was therefore ignored: the launch
#: reached for a download that was not there and the suite skipped. Two-state on purpose, and
#: classified posture-free alongside the other ``CHROME_PATH`` read: it names a program on the
#: runner's own machine, never a host, an origin or an audience, and an unusable value fails
#: the launch loudly rather than quietly widening anything.
CHROME_PATH = os.environ.get("CHROME_PATH") or None

#: Whether a browser was EXPECTED here. Three states, never two:
#:
#: * UNSET: nobody said one was expected, so a launch failure may still skip and a day-one
#:   offline checkout with no ``[demo]`` extra keeps a clean gate;
#: * SET AND EMPTY: an intent WAS expressed and it names nothing, so ``boolean_setting``
#:   refuses rather than guessing which way it pointed;
#: * SET AND TRUE: a browser was promised, so an absent extra or a failed launch FAILS.
#:
#: The last state is why this variable exists. A suite that declines to run reports exactly
#: the green a suite that ran reports, so the one place this evidence must never be allowed to
#: skip is the place that installed a browser on purpose.
BROWSER_REQUIRED = boolean_setting("DEMO_BROWSER_REQUIRED")


def _playwright_api() -> Any:
    """The pinned Playwright API, skipping only when nothing promised a browser."""
    if BROWSER_REQUIRED:
        # A browser was promised, so a missing [demo] extra is a broken promise. Let the
        # ImportError travel instead of converting it into a green tick.
        return importlib.import_module("playwright.sync_api")
    return pytest.importorskip(
        "playwright.sync_api", reason="the pinned [demo] extra is not installed"
    )


playwright_api = _playwright_api()


def _no_browser(reason: str) -> NoReturn:
    """Skip only when nothing said a browser was expected; FAIL when something did.

    An unconditional ``pytest.skip`` here was the defect this file exists to remove, one
    layer in: a suite that declines to run reports the same green as one that ran, so the
    runner that installed a browser on purpose learned nothing from its own green tick.
    """
    if BROWSER_REQUIRED:
        pytest.fail(
            "DEMO_BROWSER_REQUIRED is set, so a browser was expected here and this suite "
            f"must not skip. {reason}",
            pytrace=False,
        )
    pytest.skip(reason)


os.environ.setdefault("MKT_CAMPAIGN_PROFILE", "local")
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import demo_server  # noqa: E402  (sibling script package, path set above)


def _num(value: Any) -> str:
    return f"{float(value):.2f}"


@pytest.fixture(scope="module")
def served() -> Iterator[tuple[str, Any]]:
    """The REAL demo server, on an ephemeral port, for the duration of the module."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), demo_server.Handler)
    server.session = demo_server.DemoSession()  # type: ignore[attr-defined]
    server.lock = threading.Lock()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", server.session  # type: ignore[attr-defined]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def page(served: tuple[str, Any]) -> Iterator[Any]:
    try:
        with playwright_api.sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True, executable_path=CHROME_PATH)
            except Exception as exc:  # pragma: no cover - environment-dependent
                _no_browser(f"no pinned browser binary available: {exc}")
            context = browser.new_context()
            yield context.new_page()
            context.close()
            browser.close()
    except NotImplementedError as exc:  # pragma: no cover - environment-dependent
        _no_browser(f"playwright cannot run here: {exc}")


def test_the_served_demo_walks_every_plan_in_a_real_browser(
    page: Any, served: tuple[str, Any]
) -> None:
    base, session = served
    page.goto(f"{base}/restart", wait_until="load")

    plans = session.plans
    assert plans, "the running app computed no plans to prove"

    for index, plan in enumerate(plans):
        bar = page.locator("[data-demo='presenter-step']")
        assert bar.get_attribute("data-step") == str(index)
        assert bar.get_attribute("data-step-count") == str(len(plans))
        assert bar.get_attribute("data-step-plan") == plan["id"]

        # Figures read out of the LIVE DOM, checked against the running app.
        header = page.locator("[data-plan]")
        mix = plan["channel_mix"]
        allocated = float(mix["allocated"])
        budget = float(plan["total_budget"])

        assert header.get_attribute("data-plan") == plan["id"]
        assert header.get_attribute("data-plan-market") == plan["market"]
        assert header.get_attribute("data-plan-vertical") == plan["vertical"]
        assert header.get_attribute("data-plan-budget") == _num(budget)
        assert header.get_attribute("data-plan-allocated") == _num(allocated)
        assert header.get_attribute("data-plan-citations") == str(len(plan["citations"]))
        assert header.get_attribute("data-plan-segments") == str(len(plan["segments"]))
        assert (
            header.get_attribute("data-plan-review")
            == str(bool(plan["requires_human_review"])).lower()
        )

        # The exact budget reconciliation: recomputed here, then read from the live DOM.
        assert abs(allocated - budget) < 0.01, "the running app failed to reconcile the budget"
        assert header.get_attribute("data-plan-reconciled") == "true"

        for panel in (
            "summary",
            "creative-brief",
            "audience",
            "channel-mix",
            "reach-frequency",
            "pacing-calendar",
            "citations",
        ):
            assert page.locator(f"[data-panel='{panel}']").count() == 1, panel

        allocation = page.locator("[data-channel-count]")
        assert allocation.get_attribute("data-channel-count") == str(len(mix["lines"]))
        assert allocation.get_attribute("data-channel-budget") == _num(budget)
        assert allocation.get_attribute("data-channel-allocated") == _num(allocated)
        assert allocation.get_attribute("data-channel-reconciled") == "true"

        rendered_channels = page.locator("[data-channel]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-channel'))"
        )
        assert rendered_channels == [line["channel"] for line in mix["lines"]]

        rendered_amounts = page.locator("[data-channel-amount]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-channel-amount'))"
        )
        assert rendered_amounts == [_num(line["amount"]) for line in mix["lines"]]
        assert abs(sum(float(a) for a in rendered_amounts) - allocated) < 0.01

        assert page.locator("[data-segment-count]").get_attribute("data-segment-count") == str(
            len(plan["segments"])
        )
        rendered_ranks = page.locator("[data-segment-rank]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-segment-rank'))"
        )
        assert rendered_ranks == [str(s["rank"]) for s in plan["segments"]]

        schedule = plan["flight_schedule"]
        legs = page.locator("[data-leg-count]")
        assert legs.get_attribute("data-leg-count") == str(len(schedule["legs"]))
        assert legs.get_attribute("data-paced-total") == _num(schedule["paced_total"])

        audit = page.locator("[data-panel-body='citations'] [data-citation-count]")
        assert audit.get_attribute("data-citation-count") == str(len(plan["citations"]))
        rendered_citations = page.locator(
            "[data-panel-body='citations'] [data-citation]"
        ).evaluate_all("els => els.map(e => e.getAttribute('data-citation'))")
        assert rendered_citations == [c["source_id"] for c in plan["citations"]]

        if index < len(plans) - 1:
            page.locator(".democtl button.next:not([disabled])").click()
            page.wait_for_load_state("load")

    assert page.locator(".democtl button.next[disabled]").count() == 1
    assert "HUMAN REVIEW REQUIRED" in page.content()


def test_the_served_pages_show_every_live_citation_title_in_the_browser(
    page: Any, served: tuple[str, Any]
) -> None:
    base, session = served
    page.goto(f"{base}/restart", wait_until="load")
    plan = session.plans[0]
    content = page.content()
    assert plan["citations"], "the running app produced no citations to prove"
    for citation in plan["citations"]:
        assert citation["title"] in content
