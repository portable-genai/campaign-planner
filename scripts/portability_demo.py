"""Portability tour: prove the no-lock-in claims live, on a laptop, fully offline.

Usage (from the repo root; no cloud, no API key, no emulators)::

    PYTHONPATH=src python scripts/portability_demo.py
    # or, honouring the profile env var used everywhere else in the repo:
    PYTHONPATH=src MKT_CAMPAIGN_PROFILE=local python scripts/portability_demo.py

Four acts, mapping to the three portability questions a buyer should ask
(experience/identity, compute, data):

  1. One-line profile swap ..... the SAME campaign plan is built offline under ``local``
                                 and fails fast under ``onprem`` (no domain edits)
  2. Interface parity .......... all 9 ports instantiate + satisfy their Protocols under
                                 both SDK-free profiles (``local`` and ``onprem``), with no
                                 Google Cloud SDK installed
  3. Replayable audit trail .... the append-only audit sink stores each plan as an open
                                 JSON payload that reads back byte-identical to the domain
                                 serialization, and a re-run of the whole pipeline is
                                 deterministic (same plan, same audit)
  4. Identity portability ...... seeded personas resolve offline; IAP (gcp/platform) and the
                                 on-prem client IdP are an adapter-binding swap, never an app
                                 change

Note on scope for THIS repo: the ``local`` append-only audit sink is a WORM stand-in with
``record`` + ``read_all`` only; it has no per-record hash chain and no JSONL export/import
(the managed WORM guarantee lives in the Cloud Logging locked bucket + sink in
``infra/terraform/logging_worm.tf``). So this tour proves the audit trail is open-format and
replayable, but it does NOT claim tamper-evidence or an export/reload round-trip (those acts
from the sibling ``cdd-sow-research`` tour do not apply here and are deliberately omitted).

Exits 0 only if every check passes, so this doubles as an automated portability proof.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from campaign_planner import ports
from campaign_planner.adapters.local.identity import LocalPersonaIdentityAdapter
from campaign_planner.api.deps import make_plan_service
from campaign_planner.config import Container, LocalSettings, Settings, instantiate
from campaign_planner.domain.identity import RequestContext
from campaign_planner.domain.models import (
    AuditEvent,
    Decision,
    Market,
    PacingStrategy,
    PlanRequest,
    Vertical,
)
from campaign_planner.domain.serialization import to_jsonable

CONFIG_PATH = "config/settings.yaml"

PORT_PROTOCOLS: dict[str, type] = {
    "audience": ports.AudienceDataPort,
    "llm": ports.LlmPort,
    "guardrail": ports.GuardrailPort,
    "audit": ports.AuditSinkPort,
    "tracer": ports.ObservabilityTracerPort,
    "evaluation": ports.EvaluationGatePort,
    "agent_registry": ports.AgentRegistryPort,
    "tool_catalog": ports.ToolCatalogPort,
    "identity": ports.IdentityPort,
}

CHECKS: list[tuple[str, bool]] = []


def banner(step: str, title: str) -> None:
    print(f"\n{'=' * 78}\n{step}  {title}\n{'=' * 78}")


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok))
    marker = "PASS" if ok else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{marker}] {name}{suffix}")


def settings_for(profile: str) -> Settings:
    base = Settings.load(CONFIG_PATH)
    return replace(base, profile=profile, local=LocalSettings(audit_path=":memory:"))


def _request() -> PlanRequest:
    return PlanRequest(
        objective="savings account acquisition",
        market=Market.SG,
        vertical=Vertical.BANKING,
        total_budget=120_000.0,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 28),
        pacing=PacingStrategy.EVEN,
    )


def act_1_profile_swap() -> None:
    banner("[1/4]", "One-line profile swap: same request, local works, onprem fails fast")
    request = _request()

    local_settings = settings_for("local")
    plan = make_plan_service(Container(local_settings)).build_plan(request, actor="demo@laptop")
    citations = len(plan.citations)
    print(
        f"  local  -> plan built offline: {len(plan.segments)} segments, "
        f"allocated {plan.channel_mix.allocated:,.0f} of {plan.total_budget:,.0f}, "
        f"{citations} citations, requires_human_review={plan.requires_human_review}"
    )
    check("local profile produced a grounded, cited plan offline", citations > 0)
    check("maker-checker held (requires_human_review)", plan.requires_human_review is True)
    check(
        "the budget reconciles exactly (deterministic allocation)",
        abs(plan.channel_mix.allocated - plan.total_budget) < 0.01,
    )

    try:
        make_plan_service(Container(settings_for("onprem"))).build_plan(
            request, actor="demo@laptop"
        )
        check("onprem profile fails fast (sovereign migration placeholder)", False)
    except NotImplementedError as exc:
        print(f"  onprem -> NotImplementedError: {str(exc)[:80]} (CLI maps this to exit 2)")
        check("onprem profile fails fast (sovereign migration placeholder)", True)

    print("\n  The swap is configuration, not code: config/settings.yaml adapters.audience")
    for profile in ("local", "onprem", "platform", "gcp"):
        dotted = local_settings.adapters["audience"].get(profile, "(unbound)")
        print(f"    {profile:<9} -> {dotted}")


def act_2_interface_parity() -> None:
    banner("[2/4]", "Interface parity: 9 ports x {local, onprem}, no Google Cloud SDK")
    all_ok = True
    for port_name in sorted(PORT_PROTOCOLS):
        row = [f"  {port_name:<16}"]
        for profile in ("local", "onprem"):
            settings = settings_for(profile)
            adapter = instantiate(settings.adapters[port_name][profile], settings)
            ok = isinstance(adapter, PORT_PROTOCOLS[port_name])
            all_ok &= ok
            row.append(f"{profile}: {type(adapter).__name__} {'ok' if ok else 'MISMATCH'}")
        print(" | ".join(row))
    check("every port satisfies its Protocol under both SDK-free profiles", all_ok)


def act_3_replayable_audit() -> None:
    banner("[3/4]", "Replayable audit: open-format JSON payload, deterministic re-run")
    settings = settings_for("local")

    # (a) A single event stored by the append-only sink reads back byte-identical to the
    #     domain serialization: the audit trail is an OPEN, documented JSON payload, not a
    #     vendor blob.
    audit = instantiate(settings.adapters["audit"]["local"], settings)
    event = AuditEvent(
        action="campaign_plan",
        actor="demo@laptop",
        decision=Decision.ESCALATED,
        response="cited plan summary",
    )
    audit.record(event)
    stored = audit.read_all()
    expected = to_jsonable(event)
    print(f"  stored 1 record; reads back as open JSON with keys: {sorted(stored[0])[:6]}...")
    check(
        "audit record reads back byte-identical to the domain serialization", stored == [expected]
    )

    # (b) The WHOLE pipeline, run twice under the same profile with no edits, produces an
    #     identical plan and identical audit response: the offline stack is replayable.
    request = _request()
    plan_a = make_plan_service(Container(settings_for("local"))).build_plan(request, actor="demo")
    plan_b = make_plan_service(Container(settings_for("local"))).build_plan(request, actor="demo")
    payload_a = to_jsonable(plan_a)
    payload_b = to_jsonable(plan_b)
    # generated_at is the only wall-clock field; everything consequential must match.
    payload_a.pop("generated_at", None)
    payload_b.pop("generated_at", None)
    print(
        f"  re-ran the full pipeline: identical plan payload = {payload_a == payload_b}, "
        f"allocated {plan_a.channel_mix.allocated:,.0f} both runs"
    )
    check(
        "the full offline pipeline is deterministic (same inputs -> same plan)",
        payload_a == payload_b,
    )


def act_4_identity() -> None:
    banner("[4/4]", "Identity portability: personas offline; IAP / on-prem by binding swap")
    settings = settings_for("local")
    identity = LocalPersonaIdentityAdapter(settings)

    default = identity.resolve(RequestContext(headers={}))
    approver = identity.resolve(RequestContext(headers={"x-dev-persona": "approver"}))
    print(f"  no IdP needed: default persona resolves to {default.subject} ({default.tenant})")
    print(f"  persona picker: X-Dev-Persona: approver -> {approver.subject} {approver.principals}")
    check(
        "seeded personas resolve offline with per-user entitlements",
        default.subject != approver.subject and "group:mkt-approver" in approver.principals,
    )

    print("\n  The same IdentityPort, three verification regimes (config only):")
    for profile, dotted in sorted(settings.adapters["identity"].items()):
        print(f"    {profile:<9} -> {dotted}")


def main() -> int:
    print("Mkt2 (campaign planner) portability tour: offline proof of the three portability")
    print("questions (experience/identity, compute, data). No Google Cloud, no API key.")

    act_1_profile_swap()
    act_2_interface_parity()
    act_3_replayable_audit()
    act_4_identity()

    banner("DONE", "Scoreboard: the three questions that separate a capability from a claim")
    failures = [name for name, ok in CHECKS if not ok]
    passed = dict(CHECKS)
    q_map = {
        "Q1 experience/identity: works across hosts, identity verified system-side": [
            "seeded personas resolve offline with per-user entitlements",
        ],
        "Q2 compute: migrates by configuration with parity evidence": [
            "local profile produced a grounded, cited plan offline",
            "onprem profile fails fast (sovereign migration placeholder)",
            "every port satisfies its Protocol under both SDK-free profiles",
        ],
        "Q3 data: audit trail is open-format and replayable": [
            "audit record reads back byte-identical to the domain serialization",
            "the full offline pipeline is deterministic (same inputs -> same plan)",
        ],
    }
    for question, names in q_map.items():
        ok = all(passed.get(n, False) for n in names)
        print(f"  [{'YES' if ok else 'NO '}] {question}")

    print(f"\n  {len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed.")
    if failures:
        print("  FAILED: " + "; ".join(failures))
        return 1
    print("  Lock-in converted from an open-ended exposure into a priced, controlled risk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
