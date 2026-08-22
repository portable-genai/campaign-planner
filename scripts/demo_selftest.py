#!/usr/bin/env python3
"""Headless guard for every presenter-paced campaign-planner demo step.

Two stages, both executed, neither compared against hard-coded prose:

1. **In-process** -- the real :class:`DemoSession` computes all four live plans and
   renders every presenter step.
2. **Served** -- the real ``ThreadingHTTPServer`` is started on an ephemeral port and the
   whole presenter journey is driven over HTTP with ``POST /advance``. Every figure
   asserted at this stage is read out of the SERVED bytes through the stable ``data-*``
   evidence hooks and compared with what the RUNNING app computed, so a renderer that
   stops emitting a figure, a server that stops advancing, or a hook that gets renamed
   all fail here. A check that never served a byte cannot see whether serving works.

The headless-browser journey over the same served pages lives in
``tests/browser/test_served_demo_ui.py`` and needs the pinned ``[demo]`` extra.
"""

from __future__ import annotations

import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from demo_server import DemoSession, Handler


def _hook(html: str, attribute: str) -> str:
    """Read one stable ``data-*`` evidence hook out of served markup."""
    match = re.search(rf"{attribute}='([^']*)'", html) or re.search(rf'{attribute}="([^"]*)"', html)
    assert match, f"evidence hook {attribute} is missing from the served page"
    return match.group(1)


def _hooks(html: str, attribute: str) -> list[str]:
    return re.findall(rf"{attribute}='([^']*)'", html) or re.findall(
        rf'{attribute}="([^"]*)"', html
    )


def _num(value: object) -> str:
    return f"{float(value):.2f}"  # type: ignore[arg-type]


def check_in_process() -> None:
    session = DemoSession()
    assert len(session.plans) == 4
    for step, plan in enumerate(session.plans, 1):
        assert plan["requires_human_review"] is True
        assert plan["citations"]
        assert abs(plan["channel_mix"]["allocated"] - plan["total_budget"]) < 0.01
        page = session.render()
        assert f"Step {step}/{len(session.plans)}" in page
        assert "HUMAN REVIEW REQUIRED" in page
        if step < len(session.plans):
            session.advance()
    assert session.at_end
    session.reset()
    assert session.idx == 0
    print("PASS demo self-test: 4/4 live campaign plans rendered, advanced, and reset")


def _assert_served_plan(page: str, plan: dict) -> None:
    """Every figure below is read from served bytes and checked against the running app."""
    mix = plan["channel_mix"]
    allocated = float(mix["allocated"])
    budget = float(plan["total_budget"])

    assert _hook(page, "data-plan") == plan["id"]
    assert _hook(page, "data-plan-market") == plan["market"]
    assert _hook(page, "data-plan-vertical") == plan["vertical"]
    assert _hook(page, "data-plan-budget") == _num(budget)
    assert _hook(page, "data-plan-allocated") == _num(allocated)
    assert _hook(page, "data-plan-citations") == str(len(plan["citations"]))
    assert _hook(page, "data-plan-segments") == str(len(plan["segments"]))
    assert _hook(page, "data-plan-review") == str(bool(plan["requires_human_review"])).lower()

    # The exact budget reconciliation, asserted on the served page AND recomputed here,
    # so a renderer that hard-codes "true" while the engine drifts still fails.
    assert abs(allocated - budget) < 0.01, "the running app failed to reconcile the budget"
    assert _hook(page, "data-plan-reconciled") == "true"
    assert _hook(page, "data-channel-reconciled") == "true"
    assert _hook(page, "data-channel-budget") == _num(budget)
    assert _hook(page, "data-channel-allocated") == _num(allocated)

    panels = _hooks(page, "data-panel")
    for required in (
        "summary",
        "creative-brief",
        "audience",
        "channel-mix",
        "reach-frequency",
        "pacing-calendar",
        "citations",
    ):
        assert required in panels, f"served page lost the {required} panel hook"

    lines = mix["lines"]
    assert _hook(page, "data-channel-count") == str(len(lines))
    assert _hooks(page, "data-channel") == [line["channel"] for line in lines]
    assert _hooks(page, "data-channel-amount") == [_num(line["amount"]) for line in lines]
    # The per-channel allocations must themselves add up to what the header claims.
    served_total = sum(float(a) for a in _hooks(page, "data-channel-amount"))
    assert abs(served_total - allocated) < 0.01, "served channel lines do not add to the allocation"

    assert _hook(page, "data-segment-count") == str(len(plan["segments"]))
    assert _hooks(page, "data-segment-rank") == [str(s["rank"]) for s in plan["segments"]]

    schedule = plan["flight_schedule"]
    assert _hook(page, "data-leg-count") == str(len(schedule["legs"]))
    assert _hook(page, "data-pacing-strategy") == schedule["strategy"]
    assert _hook(page, "data-paced-total") == _num(schedule["paced_total"])

    assert _hook(page, "data-kpi-value") == _num(budget)

    # The audit panel: every live citation the running app produced is on the page.
    assert plan["citations"], "the running app produced no citations to prove"
    parts = page.split("data-panel-body='citations'")
    assert len(parts) == 2, "the served page lost its all-citations audit panel"
    audit = parts[1]
    assert _hook(audit, "data-citation-count") == str(len(plan["citations"]))
    served_citations = _hooks(audit, "data-citation")
    for citation in plan["citations"]:
        assert citation["source_id"] in served_citations
        assert citation["title"] in audit


def check_served() -> None:
    """Drive the REAL demo server over HTTP and assert live figures from served bytes."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.session = DemoSession()  # type: ignore[attr-defined]
    server.lock = threading.Lock()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    session: DemoSession = server.session  # type: ignore[attr-defined]

    try:
        for index in range(len(session.plans)):
            with urllib.request.urlopen(f"{base}/", timeout=20) as response:  # noqa: S310
                assert response.status == 200
                page = response.read().decode("utf-8")

            # The served page is at the step the served app believes it is at.
            assert _hook(page, "data-step") == str(index), f"served step marker is not {index}"
            assert _hook(page, "data-step-count") == str(len(session.plans))
            assert _hook(page, "data-demo") == "presenter-step"
            assert "HUMAN REVIEW REQUIRED" in page

            _assert_served_plan(page, session.plans[index])

            if index < len(session.plans) - 1:
                request = urllib.request.Request(f"{base}/advance", method="POST", data=b"")
                with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
                    assert response.status in (200, 303)
            else:
                assert "Demo complete" in page

        # Restart must serve too, and must put the running app back on the first plan.
        with urllib.request.urlopen(f"{base}/restart", timeout=20) as response:  # noqa: S310
            restarted = response.read().decode("utf-8")
        assert response.status == 200
        assert _hook(restarted, "data-step") == "0"
        assert session.idx == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print(
        "PASS served: every presenter step, panel hook, budget reconciliation and "
        "citation read back over HTTP from the running demo server"
    )


def main() -> int:
    check_in_process()
    check_served()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
