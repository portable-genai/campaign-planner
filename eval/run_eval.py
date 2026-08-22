#!/usr/bin/env python3
"""Offline evaluation gate for the D2 Campaign Planning system (A4).

This is the **promotion gate**: CI runs it on every change and the build fails if the
agent's campaign plans fall below the model-risk thresholds agreed for a campaign-planning
agent (see ``eval/rubrics/*.yaml``)::

    plan_groundedness >= 0.80   (every plan carries citations on its figures)
    citation_accuracy >= 0.90   (cites only retrieved / derived sources)
    budget_accuracy   >= 0.99   (allocation + pacing reconcile to the budget exactly)
    review_safety     >= 0.99   (every plan requires human review; maker-checker)

Two evaluators, one gate
------------------------
* **Production evaluator** — the **Gen AI evaluation service** on the Gemini Enterprise
  Agent Platform, wired in as ``EvaluationGatePort`` ->
  ``campaign_planner.adapters.gcp.genai_eval:GenAiEvalAdapter``. It needs GCP credentials.
  Select it with ``--use-gcp``.

* **Offline evaluator (default)** — a deterministic gate in this file. It needs **no GCP
  credentials and no Google Cloud SDK**, runs the real ``CampaignPlanService`` against the
  local (offline) adapters over the golden set, and computes the four metrics. This is what
  guards the merge in CI.

Usage::

    python eval/run_eval.py                      # offline gate (CI)
    python eval/run_eval.py --dataset path.jsonl # custom golden set
    python eval/run_eval.py --use-gcp            # route through GenAiEvalAdapter

Exit code is ``0`` iff ``EvalReport.passed`` (every metric meets its threshold).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Domain models / config are pure-stdlib + the local adapters are SDK-free, so this script
# runs in the local / on-prem / test profile with no Google Cloud SDK installed.
# The --mode smoke|gate scaffold + aligned report rendering come from the shared
# agent-eval-kit commons; this script keeps only its own offline
# evaluator and gate runner.
from agent_eval_kit import eval_main

from campaign_planner.domain.models import (
    EvalMetricResult,
    EvalReport,
    Market,
    PacingStrategy,
    Plan,
    PlanRequest,
    Vertical,
)

THRESHOLDS: dict[str, float] = {
    "plan_groundedness": 0.80,
    "citation_accuracy": 0.90,
    "budget_accuracy": 0.99,
    "review_safety": 0.99,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_plans.jsonl"
_START = date(2026, 7, 1)
_END = date(2026, 7, 28)
_TOLERANCE = 0.05  # currency rounding tolerance for reconciliation checks


# --------------------------------------------------------------------------- #
# Golden dataset
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class GoldenExample:
    id: str
    objective: str
    market: str
    vertical: str
    total_budget: float
    pacing: str


def load_golden(path: Path) -> list[GoldenExample]:
    examples: list[GoldenExample] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        examples.append(
            GoldenExample(
                id=str(obj.get("id", f"example-{lineno}")),
                objective=str(obj["objective"]),
                market=str(obj["market"]),
                vertical=str(obj["vertical"]),
                total_budget=float(obj["total_budget"]),
                pacing=str(obj.get("pacing", "even")),
            )
        )
    if not examples:
        raise SystemExit(f"{path}: golden dataset is empty")
    return examples


def load_thresholds_from_rubrics() -> dict[str, float]:
    """Read thresholds from ``eval/rubrics/*.yaml`` when PyYAML is available."""
    thresholds = dict(THRESHOLDS)
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return thresholds
    rubric_dir = _REPO_ROOT / "eval" / "rubrics"
    for name in ("groundedness.yaml", "budget_accuracy.yaml"):
        rubric_path = rubric_dir / name
        if not rubric_path.exists():
            continue
        doc = yaml.safe_load(rubric_path.read_text(encoding="utf-8")) or {}
        metric = doc.get("metric")
        if isinstance(metric, str) and "threshold" in doc:
            thresholds[metric] = float(doc["threshold"])
        for companion, spec in (doc.get("companion_metrics") or {}).items():
            if isinstance(spec, dict) and "threshold" in spec:
                thresholds[str(companion)] = float(spec["threshold"])
    return thresholds


# --------------------------------------------------------------------------- #
# Service wiring (the real CampaignPlanService over the local offline adapters)
# --------------------------------------------------------------------------- #
def _make_service():  # type: ignore[no-untyped-def]
    from campaign_planner.api.deps import make_plan_service
    from campaign_planner.config import Container, LocalSettings, Settings

    base = Settings.load(str(_REPO_ROOT / "config" / "settings.yaml"))
    settings = Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        models=base.models,
        bigquery=base.bigquery,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(audit_path=":memory:"),
        policy=base.policy,
        markets=base.markets,
        adapters=base.adapters,
    )
    container = Container(settings)
    return make_plan_service(container)


# --------------------------------------------------------------------------- #
# Heuristic scorers
# --------------------------------------------------------------------------- #
def score_groundedness(plan: Plan) -> float:
    """Every plan with a budget allocation must carry at least one citation."""
    return 1.0 if plan.citations else 0.0


def score_citation_accuracy(plan: Plan) -> float:
    """No cited source outside the plan's own derived evidence set."""
    cited = {c.source_id for c in plan.citations}
    if not cited:
        return 0.0
    allowed: set[str] = set()
    for s in plan.segments:
        allowed.update(c.source_id for c in s.citations)
    for line in plan.channel_mix.lines:
        allowed.update(c.source_id for c in line.citations)
    return round(len(cited & allowed) / len(cited), 4)


def score_budget_accuracy(plan: Plan) -> float:
    """The allocation and the pacing must each reconcile to the total budget."""
    alloc_ok = abs(plan.channel_mix.allocated - plan.total_budget) <= _TOLERANCE
    pace_ok = abs(plan.flight_schedule.paced_total - plan.total_budget) <= _TOLERANCE
    return 1.0 if (alloc_ok and pace_ok) else 0.0


def score_review_safety(plan: Plan) -> float:
    return 1.0 if plan.requires_human_review else 0.0


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
@dataclass
class _PerMetric:
    scores: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0


def run_offline(dataset: Path, thresholds: dict[str, float]) -> EvalReport:
    examples = load_golden(dataset)
    service = _make_service()
    agg: dict[str, _PerMetric] = {m: _PerMetric() for m in THRESHOLDS}
    print(f"Running offline eval gate over {len(examples)} golden plans (CampaignPlanService).\n")
    for ex in examples:
        request = PlanRequest(
            objective=ex.objective,
            market=Market(ex.market),
            vertical=Vertical(ex.vertical),
            total_budget=ex.total_budget,
            start_date=_START,
            end_date=_END,
            pacing=PacingStrategy(ex.pacing),
        )
        plan = service.build_plan(request, actor="eval-bot")
        agg["plan_groundedness"].scores.append(score_groundedness(plan))
        agg["citation_accuracy"].scores.append(score_citation_accuracy(plan))
        agg["budget_accuracy"].scores.append(score_budget_accuracy(plan))
        agg["review_safety"].scores.append(score_review_safety(plan))

    order = ("plan_groundedness", "citation_accuracy", "budget_accuracy", "review_safety")
    results = tuple(
        EvalMetricResult(
            metric=metric,
            score=round(agg[metric].mean, 4),
            threshold=thresholds.get(metric, THRESHOLDS[metric]),
            passed=round(agg[metric].mean, 4) >= thresholds.get(metric, THRESHOLDS[metric]),
        )
        for metric in order
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(examples))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    """Promotion verdict via EvaluationGatePort (platform = Hrz4, gcp = Gen AI evals).

    Fails closed on the reconciled evaluate + gate result. Refuses to run outside the
    platform/gcp profiles so the offline smoke result is never relabelled a promotion pass.
    """
    from campaign_planner.config import Settings, build_container

    settings = Settings.load()
    if settings.profile not in ("platform", "gcp"):
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            "MKT_CAMPAIGN_PROFILE=platform or gcp "
            f"(got {settings.profile!r}); run --mode smoke for the offline pre-merge check."
        )
    container = build_container(settings)
    gate = container.evaluation
    report = gate.evaluate(str(dataset))
    if not isinstance(report, EvalReport):  # pragma: no cover - defensive
        raise SystemExit("EvaluationGatePort.evaluate did not return an EvalReport")
    gate_passed = bool(gate.gate(str(dataset)))
    return report, gate_passed


def main(argv: list[str] | None = None) -> int:
    """Dispatch --mode via the shared eval_main scaffold (fail-closed exit codes).

    ``--use-gcp`` (the pre-split flag for the production evaluator) is kept as an alias
    for ``--mode gate``.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if "--use-gcp" in args:
        args = [a for a in args if a != "--use-gcp"] + ["--mode", "gate"]
    return eval_main(
        smoke=lambda dataset: run_offline(dataset, load_thresholds_from_rubrics()),
        gate=run_gate,
        default_dataset=DEFAULT_DATASET,
        description="Offline / platform evaluation gate for D2 (A4 / P-08).",
        smoke_label="offline heuristic (no GCP creds)",
        gate_label="promotion gate (EvaluationGatePort: Hrz4 / Gen AI evals)",
        argv=args,
    )


if __name__ == "__main__":
    raise SystemExit(main())
