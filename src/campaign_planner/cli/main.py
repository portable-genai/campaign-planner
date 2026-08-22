"""``mkt-campaign`` — the Typer CLI for the D2 Campaign Planning system.

A thin presentation layer over the domain services. It owns no business logic: every command
builds the wiring from :func:`campaign_planner.api.deps.make_plan_service`, invokes one
domain service, and pretty-prints the cited result.

Design constraints honoured here:

* **Import-safe.** Importing this module (the ``[project.scripts]`` entry point, or
  ``--help``) must never pull in FastAPI, uvicorn or the Google Cloud SDKs. They are imported
  lazily inside command bodies, so the on-prem / local / test profile (which installs no
  Google Cloud SDK) can still load the CLI.
* **Profile-aware.** ``MKT_CAMPAIGN_PROFILE`` selects the adapter stack. The ``onprem``
  profile binds placeholder adapters that raise ``NotImplementedError``; the CLI then fails
  clearly (exit code 2) naming the migration target.
* **Citations are first-class.** Every artifact prints with source-and-page provenance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..domain.models import Citation, Plan

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "D2 Campaign Planning and Budget Allocation — cited campaign plans (audience, "
        "channel-mix budget allocation, reach / frequency, pacing), generic across banking "
        "and online retail and the JP/AU/SG markets."
    ),
)

_PROFILE_EXIT = 2
_RUNTIME_EXIT = 1
_CLI_ACTOR = "cli:operator"


def _fail(message: str, *, code: int = _RUNTIME_EXIT) -> Any:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _run(action: str, fn: Any) -> Any:
    """Execute ``fn`` and translate adapter failures into clean CLI errors."""
    from ..config import Settings

    profile = Settings.load().profile
    try:
        return fn()
    except NotImplementedError as exc:
        detail = str(exc) or "method not implemented"
        _fail(
            f"'{action}' is not available under profile '{profile}'. "
            f"This profile uses placeholder adapters (migration target): {detail}",
            code=_PROFILE_EXIT,
        )
    except KeyError as exc:
        _fail(f"'{action}' has no adapter wired for profile '{profile}': {exc}", code=_PROFILE_EXIT)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI boundary: no tracebacks to operators
        _fail(f"'{action}' failed: {type(exc).__name__}: {exc}", code=_RUNTIME_EXIT)


# --------------------------------------------------------------------------- #
# Pretty-printing
# --------------------------------------------------------------------------- #
def _fmt_citation(c: Citation) -> str:
    page = f" p.{c.page}" if c.page is not None else ""
    st = c.source_type.value if hasattr(c.source_type, "value") else str(c.source_type)
    url = f" — {c.url}" if c.url else ""
    return f"[{c.source_id}, {st}{page}]{url}"


def _echo_citations(citations: tuple[Citation, ...], indent: str = "  ") -> None:
    if not citations:
        typer.secho(f"{indent}(no citations)", fg=typer.colors.YELLOW)
        return
    typer.secho(f"{indent}Citations:", bold=True)
    for c in citations:
        typer.echo(f"{indent}  - {_fmt_citation(c)}")


def _echo_review_banner(requires_review: bool) -> None:
    if requires_review:
        typer.secho(
            "  [HUMAN REVIEW REQUIRED] maker-checker gate — do not commit any spend until a "
            "qualified marketer / finance approver signs off on this plan.",
            fg=typer.colors.YELLOW,
            bold=True,
        )


def _echo_plan(plan: Plan) -> None:
    typer.secho(f"\nCAMPAIGN PLAN: {plan.objective}", bold=True)
    typer.echo(f"  id          : {plan.id}")
    typer.echo(f"  market      : {plan.market.value}")
    typer.echo(f"  vertical    : {plan.vertical.value}")
    typer.echo(f"  total budget: {plan.total_budget:,.0f}")
    _echo_review_banner(plan.requires_human_review)

    typer.secho("\n  Summary:", bold=True)
    typer.echo(f"    {plan.summary}")

    typer.secho("\n  Creative brief:", bold=True)
    typer.echo(f"    {plan.creative_brief}")

    typer.secho("\n  Selected audience segments (ranked):", bold=True)
    for s in plan.segments:
        typer.echo(
            f"    {s.rank}. {s.segment.name}: score {s.score:.2f} "
            f"({s.segment.consented_reachable:,} consented-reachable)"
        )

    typer.secho("\n  Channel mix (deterministic allocation):", bold=True)
    mix = plan.channel_mix
    for line in mix.lines:
        typer.echo(
            f"    - {line.channel.value:8s} {line.amount:>12,.0f} "
            f"({line.share * 100:4.0f}%)  {line.expected_conversions:>8,.0f} conv  "
            f"CAC {line.expected_cost_per_conversion:,.2f}"
        )
    typer.echo(
        f"    => allocated {mix.allocated:,.0f}, "
        f"{mix.expected_conversions:,.0f} conversions, "
        f"blended CAC {mix.blended_cost_per_conversion:,.2f}"
    )

    rf = plan.reach_frequency
    typer.secho("\n  Reach / frequency:", bold=True)
    typer.echo(
        f"    unique reach {rf.unique_reach:,} of {rf.addressable:,} addressable "
        f"({rf.reach_pct * 100:.1f}%); avg freq {rf.average_frequency:.2f}; "
        f"{rf.effective_reach:,} at {rf.effective_frequency}+"
    )

    fs = plan.flight_schedule
    typer.secho(f"\n  Flight schedule ({fs.strategy.value}):", bold=True)
    for leg in fs.legs:
        typer.echo(
            f"    leg {leg.index + 1}: {leg.start_date} -> {leg.end_date}  "
            f"{leg.amount:>12,.0f} ({leg.weight * 100:.0f}%)"
        )

    typer.secho("", nl=True)
    _echo_citations(plan.citations)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def plan(
    objective: str = typer.Argument(
        ..., help="The campaign objective, e.g. 'savings acquisition'."
    ),
    market: str = typer.Option("SG", "--market", "-m", help="Market: JP | AU | SG."),
    vertical: str = typer.Option(
        "banking", "--vertical", "-v", help="Vertical: banking | online_retail."
    ),
    budget: float = typer.Option(100_000.0, "--budget", "-b", help="Total budget."),
    start: str = typer.Option("2026-07-01", "--start", help="Flight start date (ISO)."),
    end: str = typer.Option("2026-07-28", "--end", help="Flight end date (ISO)."),
    legs: int = typer.Option(4, "--legs", help="Number of pacing legs."),
    pacing: str = typer.Option(
        "even", "--pacing", help="Pacing: even | front_loaded | back_loaded."
    ),
    max_segments: int = typer.Option(5, "--max-segments", help="Max audience segments."),
) -> None:
    """Build a cited campaign plan for an objective in a market and vertical."""
    from datetime import date

    from ..api.deps import make_plan_service
    from ..domain.models import Market, PacingStrategy, PlanRequest, Vertical

    def go() -> Plan:
        request = PlanRequest(
            objective=objective,
            market=Market(market),
            vertical=Vertical(vertical),
            total_budget=budget,
            start_date=date.fromisoformat(start),
            end_date=date.fromisoformat(end),
            flight_legs=legs,
            pacing=PacingStrategy(pacing),
            max_segments=max_segments,
        )
        return make_plan_service().build_plan(request, actor=_CLI_ACTOR)

    result = _run("plan", go)
    _echo_plan(result)


if __name__ == "__main__":  # pragma: no cover
    app()
