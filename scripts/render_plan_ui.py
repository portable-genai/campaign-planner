#!/usr/bin/env python3
"""Render the D2 audit-first console from the demo JSON into static HTML pages.

Server-side, dependency-free rendering of a cited :class:`Plan` (summary, creative brief,
selected audience segments with provenance, the channel-mix budget allocation, the reach /
frequency estimate, the pacing flight schedule, the source list, and the maker-checker
"human review required" banner). It reuses the exact palette of the thin Next.js console so
screenshots match the live UI, and runs entirely offline over the obviously-fictional
synthetic plans written by ``scripts/demo.py``.

    PYTHONPATH=src python scripts/demo.py
    PYTHONPATH=src python scripts/render_plan_ui.py scripts/out

Writes ``index.html`` (a small chooser) plus one ``<plan-id>.html`` per plan. The rendering
functions are also imported by ``scripts/demo_server.py`` for the presenter demo.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

SOURCE_LABEL = {
    "audience_data": "AUDIENCE",
    "benchmark": "BENCHMARK",
    "rule": "RULE",
    "policy": "POLICY",
    "internal": "INTERNAL",
    "other": "SRC",
}
MARKET_LABEL = {"JP": "Japan", "AU": "Australia", "SG": "Singapore"}
VERTICAL_LABEL = {"banking": "Banking", "online_retail": "Online retail"}

CSS = """
:root{--ink-50:#f5f7fa;--ink-100:#e6ebf2;--ink-200:#cdd7e4;--ink-300:#a6b6cc;
--ink-400:#7790ae;--ink-500:#546b8b;--ink-600:#3f5470;--ink-700:#33445b;--ink-800:#1f2a3a;
--brand-50:#eef4ff;--brand-100:#dbe7ff;--brand-600:#2945d6;--brand-700:#2237ad;
--ok:#059669;--warn:#d97706;--warn-bg:#fffbeb;
--shadow:0 1px 2px rgba(11,16,26,.06),0 8px 24px rgba(11,16,26,.06);}
*{box-sizing:border-box}
body{margin:0;background:var(--ink-50);color:var(--ink-800);
font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
font-size:14px;line-height:1.5;padding:24px 18px}
.wrap{max-width:920px;margin:0 auto}
h1{font-size:18px;margin:0 0 2px}
.sub{color:var(--ink-500);font-size:13px;margin:0 0 16px}
.sub b{color:var(--ink-800)}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:999px;
border:1px solid var(--brand-100);background:var(--brand-50);color:var(--brand-700);margin-right:6px}
.panel{border:1px solid var(--ink-200);background:#fff;border-radius:10px;box-shadow:var(--shadow);margin-bottom:16px}
.panel>h2{border-bottom:1px solid var(--ink-100);padding:11px 16px;margin:0;font-size:13px;font-weight:600;color:var(--ink-800)}
.panel>.body{padding:16px}
.review{border:1px solid #fcd34d;background:var(--warn-bg);color:#92400e;border-radius:8px;padding:8px 12px;font-size:12px;font-weight:600;margin-bottom:14px}
.summary{font-size:14px;line-height:1.6}
.row{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--ink-100)}
.row:last-child{border-bottom:0}
.muted{color:var(--ink-400);font-size:12px}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.kpi{flex:1;min-width:130px;border:1px solid var(--ink-200);border-radius:8px;padding:10px 12px;background:var(--ink-50)}
.kpi .v{font-size:18px;font-weight:700;color:var(--ink-800)}
.kpi .l{font-size:11px;color:var(--ink-500)}
.bar{flex:0 0 120px;height:8px;border-radius:6px;background:var(--ink-100);border:1px solid var(--ink-200);overflow:hidden}
.bar>span{display:block;height:100%;background:linear-gradient(90deg,#3a60f0,#2945d6)}
.cites{margin-top:8px;display:flex;flex-direction:column;gap:6px}
.cite{display:flex;gap:8px;align-items:baseline;border:1px solid var(--ink-200);background:var(--ink-50);border-radius:7px;padding:7px 10px}
.cite .src{font-family:ui-monospace,Menlo,monospace;font-size:11px;font-weight:600;color:var(--brand-700);background:var(--brand-50);border:1px solid var(--brand-100);border-radius:5px;padding:1px 6px;white-space:nowrap}
.cite .title{font-size:12px;color:var(--ink-700)}
.cite .id{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--ink-500);margin-left:auto;white-space:nowrap}
.cite a{color:var(--brand-600);text-decoration:none;font-size:11px}
a.choose{display:block;padding:10px 12px;border:1px solid var(--ink-200);border-radius:8px;background:#fff;margin-bottom:8px;text-decoration:none;color:var(--ink-800)}
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _money(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return esc(value)


def _num(value: Any) -> str:
    """Canonical 2-dp figure for a ``data-*`` evidence hook (F2).

    The visible figures are rounded for reading; the hooks carry the exact computed
    number so an assertion compares what the app allocated, not what it displayed.
    """
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return esc(value)


def slug(title: str) -> str:
    """Stable, styling-independent identifier for a result panel (F2 evidence hook)."""
    return "".join(ch if ch.isalnum() else "-" for ch in title.lower()).strip("-")


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body>"
        f"<div class='wrap'>{body}</div></body></html>"
    )


def _citations(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return "<div class='muted'>(no citations)</div>"
    rows = []
    for c in citations:
        label = SOURCE_LABEL.get(str(c.get("source_type")), "SRC")
        url = c.get("url") or ""
        link = f"<a href='{esc(url)}'>open</a>" if url else ""
        rows.append(
            f"<div class='cite' data-citation='{esc(c.get('source_id'))}' "
            f"data-citation-type='{esc(c.get('source_type'))}'>"
            f"<span class='src'>{esc(label)}</span>"
            f"<span class='title'>{esc(c.get('title'))}</span>"
            f"<span class='id'>{esc(c.get('source_id'))}</span>{link}"
            "</div>"
        )
    return f"<div class='cites' data-citation-count='{len(citations)}'>" + "".join(rows) + "</div>"


def _panel(title: str, body: str, name: str | None = None) -> str:
    """One result panel, tagged with a stable ``data-panel`` slug (F2 evidence hook).

    ``name`` pins the slug when the visible title carries a variable (the pacing
    calendar names its strategy), so the hook survives a wording change.
    """
    panel = name or slug(title)
    return (
        f"<div class='panel' data-panel='{esc(panel)}'><h2>{esc(title)}</h2>"
        f"<div class='body' data-panel-body='{esc(panel)}'>{body}</div></div>"
    )


def render_plan(data: dict[str, Any]) -> str:
    """Render one cited Plan dict into a standalone HTML page."""
    market = MARKET_LABEL.get(str(data.get("market")), str(data.get("market")))
    vertical = VERTICAL_LABEL.get(str(data.get("vertical")), str(data.get("vertical")))
    mix_hooks = data.get("channel_mix") or {}
    allocated = float(mix_hooks.get("allocated") or 0.0)
    budget = float(data.get("total_budget") or 0.0)
    head = (
        # F2 evidence hooks: the load-bearing figures of a plan, exact rather than
        # display-rounded, so an assertion sees what the engine computed.
        f"<div data-plan='{esc(data.get('id'))}' data-plan-market='{esc(data.get('market'))}' "
        f"data-plan-vertical='{esc(data.get('vertical'))}' "
        f"data-plan-budget='{_num(budget)}' "
        f"data-plan-allocated='{_num(allocated)}' "
        f"data-plan-reconciled='{str(abs(allocated - budget) < 0.01).lower()}' "
        f"data-plan-citations='{len(data.get('citations') or [])}' "
        f"data-plan-segments='{len(data.get('segments') or [])}' "
        f"data-plan-review='{str(bool(data.get('requires_human_review'))).lower()}'></div>"
        f"<h1>Campaign plan — {esc(data.get('objective'))}</h1>"
        f"<p class='sub'><span class='pill'>{esc(market)}</span>"
        f"<span class='pill'>{esc(vertical)}</span> id <b>{esc(data.get('id'))}</b></p>"
    )
    review = ""
    if data.get("requires_human_review"):
        review = (
            "<div class='review'>HUMAN REVIEW REQUIRED — maker-checker gate. Do not commit "
            "any spend on this plan until a qualified marketer / finance approver signs off."
            "</div>"
        )

    mix = data.get("channel_mix") or {}
    rf = data.get("reach_frequency") or {}
    kpis = (
        "<div class='kpis'>"
        f"<div class='kpi' data-kpi='total-budget' data-kpi-value='{_num(data.get('total_budget'))}'>"
        f"<div class='v'>{_money(data.get('total_budget'))}</div>"
        "<div class='l'>total budget</div></div>"
        f"<div class='kpi' data-kpi='expected-conversions' "
        f"data-kpi-value='{_num(mix.get('expected_conversions'))}'>"
        f"<div class='v'>{_money(mix.get('expected_conversions'))}</div>"
        "<div class='l'>expected conversions</div></div>"
        f"<div class='kpi' data-kpi='blended-cac' "
        f"data-kpi-value='{_num(mix.get('blended_cost_per_conversion'))}'>"
        f"<div class='v'>{_money(mix.get('blended_cost_per_conversion'))}</div>"
        "<div class='l'>blended CAC</div></div>"
        f"<div class='kpi' data-kpi='unique-reach' data-kpi-value='{_num(rf.get('unique_reach'))}'>"
        f"<div class='v'>{_money(rf.get('unique_reach'))}</div>"
        "<div class='l'>unique reach</div></div>"
        "</div>"
    )
    summary = _panel(
        "Summary", kpis + f"<div class='summary'>{esc(data.get('summary'))}</div>", "summary"
    )
    brief = _panel(
        "Creative brief (LLM-drafted, grounded)",
        f"<div class='summary'>{esc(data.get('creative_brief'))}</div>",
        "creative-brief",
    )

    seg_rows = []
    for s in data.get("segments", []):
        segment = s.get("segment") or {}
        seg_rows.append(
            f"<div class='row' data-segment='{esc(segment.get('id'))}' "
            f"data-segment-rank='{esc(s.get('rank'))}' "
            f"data-segment-score='{_num(s.get('score', 0))}'>"
            f"<div style='flex:1'><b>#{esc(s.get('rank'))} {esc(segment.get('name'))}</b> "
            f"<span class='muted'>· {_money(segment.get('consented_reachable'))} consented-reachable</span>"
            f"{_citations(s.get('citations', []))}</div>"
            f"<div class='bar'><span style='width:{int(round(float(s.get('score', 0)) * 100))}%'></span></div>"
            f"<div class='muted'>{float(s.get('score', 0)):.2f}</div></div>"
        )
    segments = _panel(
        "Selected audience (deterministic ranking)",
        f"<div data-segment-count='{len(data.get('segments', []))}'>"
        + ("".join(seg_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "audience",
    )

    line_rows = []
    for line in mix.get("lines", []):
        pct = int(round(float(line.get("share", 0)) * 100))
        line_rows.append(
            f"<div class='row' data-channel='{esc(line.get('channel'))}' "
            f"data-channel-amount='{_num(line.get('amount'))}' "
            f"data-channel-share='{_num(line.get('share', 0))}'>"
            f"<div style='flex:1'><b>{esc(line.get('channel'))}</b> "
            f"<span class='muted'>· {_money(line.get('expected_conversions'))} conv · "
            f"CAC {_money(line.get('expected_cost_per_conversion'))}</span>"
            f"{_citations(line.get('citations', []))}</div>"
            f"<div class='bar'><span style='width:{pct}%'></span></div>"
            f"<div class='muted'>{_money(line.get('amount'))} ({pct}%)</div></div>"
        )
    channel = _panel(
        "Channel mix (deterministic budget allocation)",
        # The reconciliation is the load-bearing figure of this product: every
        # allocated unit must add back up to the budget the planner was given.
        f"<div data-channel-count='{len(mix.get('lines', []))}' "
        f"data-channel-budget='{_num(budget)}' "
        f"data-channel-allocated='{_num(allocated)}' "
        f"data-channel-reconciled='{str(abs(allocated - budget) < 0.01).lower()}'>"
        + ("".join(line_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "channel-mix",
    )

    reach = _panel(
        "Reach / frequency (deterministic)",
        f"<div class='summary' data-reach-unique='{_num(rf.get('unique_reach'))}' "
        f"data-reach-frequency='{_num(rf.get('average_frequency'))}'>"
        f"{esc(rf.get('rationale'))}</div>",
        "reach-frequency",
    )

    fs = data.get("flight_schedule") or {}
    leg_rows = []
    for leg in fs.get("legs", []):
        pct = int(round(float(leg.get("weight", 0)) * 100))
        leg_rows.append(
            f"<div class='row' data-leg='{esc(leg.get('index'))}' "
            f"data-leg-amount='{_num(leg.get('amount'))}'>"
            f"<div style='flex:1'>leg {int(leg.get('index', 0)) + 1}: "
            f"<span class='muted'>{esc(leg.get('start_date'))} -> {esc(leg.get('end_date'))}</span></div>"
            f"<div class='bar'><span style='width:{pct}%'></span></div>"
            f"<div class='muted'>{_money(leg.get('amount'))} ({pct}%)</div></div>"
        )
    flight = _panel(
        f"Pacing calendar — {esc(fs.get('strategy'))} (deterministic)",
        f"<div data-leg-count='{len(fs.get('legs', []))}' "
        f"data-pacing-strategy='{esc(fs.get('strategy'))}' "
        f"data-paced-total='{_num(fs.get('paced_total'))}'>"
        + ("".join(leg_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "pacing-calendar",
    )

    sources = _panel("All citations", _citations(data.get("citations", [])), "citations")

    body = head + review + summary + brief + segments + channel + reach + flight + sources
    return _page(f"Campaign plan — {data.get('objective')}", body)


def render_index(plans: list[tuple[str, dict[str, Any]]]) -> str:
    rows = []
    for fname, data in plans:
        market = MARKET_LABEL.get(str(data.get("market")), str(data.get("market")))
        vertical = VERTICAL_LABEL.get(str(data.get("vertical")), str(data.get("vertical")))
        rows.append(
            f"<a class='choose' href='{esc(fname)}'><b>{esc(data.get('objective'))}</b> "
            f"<span class='muted'>· {esc(market)} · {esc(vertical)}</span></a>"
        )
    body = (
        "<h1>D2 Campaign Planner — demo plans</h1>"
        "<p class='sub'>Offline, obviously-fictional synthetic data. Local profile, no cloud.</p>"
        + "".join(rows)
    )
    return _page("D2 demo plans", body)


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path("scripts/out")
    plans: list[tuple[str, dict[str, Any]]] = []
    for json_path in sorted(out_dir.glob("plan-*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        html_name = json_path.stem + ".html"
        (out_dir / html_name).write_text(render_plan(data), encoding="utf-8")
        plans.append((html_name, data))
        print(f"wrote {out_dir / html_name}")
    (out_dir / "index.html").write_text(render_index(plans), encoding="utf-8")
    print(f"wrote {out_dir / 'index.html'}  ({len(plans)} plan(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
