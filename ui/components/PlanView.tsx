import type { Plan } from "@/lib/types";
import { CitationList } from "./CitationList";

const MARKET_LABEL: Record<string, string> = {
  JP: "Japan",
  AU: "Australia",
  SG: "Singapore",
};
const VERTICAL_LABEL: Record<string, string> = {
  banking: "Banking",
  online_retail: "Online retail",
};

function money(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString();
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-4 rounded-xl border border-ink-200 bg-white shadow-panel">
      <h2 className="border-b border-ink-100 px-4 py-2.5 text-[13px] font-semibold text-ink-800">
        {title}
      </h2>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Bar({ value }: { value: number }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-28 overflow-hidden rounded-md border border-ink-200 bg-ink-100">
        <div
          className="h-full bg-gradient-to-r from-brand-500 to-brand-600"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-ink-500">{pct}%</span>
    </div>
  );
}

function Kpi({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex-1 min-w-[130px] rounded-lg border border-ink-200 bg-ink-50 px-3 py-2.5">
      <div className="text-lg font-bold text-ink-800">{value}</div>
      <div className="text-[11px] text-ink-500">{label}</div>
    </div>
  );
}

export function PlanView({ plan }: { plan: Plan }) {
  const mix = plan.channel_mix;
  const rf = plan.reach_frequency;
  const fs = plan.flight_schedule;
  return (
    <div>
      <h1 className="text-lg font-semibold">Campaign plan — {plan.objective}</h1>
      <p className="mb-4 text-[13px] text-ink-500">
        <span className="mr-1.5 inline-block rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700">
          {MARKET_LABEL[plan.market] ?? plan.market}
        </span>
        <span className="mr-1.5 inline-block rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700">
          {VERTICAL_LABEL[plan.vertical] ?? plan.vertical}
        </span>
        id <b className="text-ink-800">{plan.id}</b>
      </p>

      {plan.requires_human_review ? (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
          HUMAN REVIEW REQUIRED — maker-checker gate. Do not commit any spend on this plan
          until a qualified marketer / finance approver signs off.
        </div>
      ) : null}

      <Panel title="Summary">
        <div className="mb-3 flex flex-wrap gap-2.5">
          <Kpi value={money(plan.total_budget)} label="total budget" />
          <Kpi value={money(mix.expected_conversions)} label="expected conversions" />
          <Kpi value={money(mix.blended_cost_per_conversion)} label="blended CAC" />
          <Kpi value={money(rf.unique_reach)} label="unique reach" />
        </div>
        <p className="leading-relaxed">{plan.summary}</p>
      </Panel>

      <Panel title="Creative brief (LLM-drafted, grounded)">
        <p className="leading-relaxed">{plan.creative_brief}</p>
      </Panel>

      <Panel title="Selected audience (deterministic ranking)">
        {plan.segments.length === 0 ? (
          <div className="text-xs text-ink-400">none</div>
        ) : (
          plan.segments.map((s, i) => (
            <div
              key={i}
              className="flex items-center gap-3 border-b border-ink-100 py-2 last:border-0"
            >
              <div className="flex-1">
                <b>
                  #{s.rank} {s.segment.name}
                </b>{" "}
                <span className="text-xs text-ink-400">
                  · {money(s.segment.consented_reachable)} consented-reachable
                </span>
                <CitationList citations={s.citations} />
              </div>
              <Bar value={s.score} />
            </div>
          ))
        )}
      </Panel>

      <Panel title="Channel mix (deterministic budget allocation)">
        {mix.lines.length === 0 ? (
          <div className="text-xs text-ink-400">none</div>
        ) : (
          mix.lines.map((line, i) => (
            <div
              key={i}
              className="flex items-center gap-3 border-b border-ink-100 py-2 last:border-0"
            >
              <div className="flex-1">
                <b>{line.channel}</b>{" "}
                <span className="text-xs text-ink-400">
                  · {money(line.expected_conversions)} conv · CAC{" "}
                  {money(line.expected_cost_per_conversion)}
                </span>
                <CitationList citations={line.citations} />
              </div>
              <div className="text-right text-xs text-ink-500">
                {money(line.amount)}
                <Bar value={line.share} />
              </div>
            </div>
          ))
        )}
        <div className="mt-2 text-xs text-ink-500">
          allocated <b className="text-ink-700">{money(mix.allocated)}</b> of{" "}
          {money(mix.total_budget)}
        </div>
      </Panel>

      <Panel title="Reach / frequency (deterministic)">
        <p className="leading-relaxed text-[13px]">{rf.rationale}</p>
      </Panel>

      <Panel title={`Pacing calendar — ${fs.strategy} (deterministic)`}>
        {fs.legs.map((leg, i) => (
          <div
            key={i}
            className="flex items-center gap-3 border-b border-ink-100 py-2 last:border-0"
          >
            <div className="flex-1">
              leg {leg.index + 1}{" "}
              <span className="text-xs text-ink-400">
                · {leg.start_date} → {leg.end_date}
              </span>
            </div>
            <div className="text-right text-xs text-ink-500">
              {money(leg.amount)}
              <Bar value={leg.weight} />
            </div>
          </div>
        ))}
      </Panel>

      <Panel title="All citations">
        <CitationList citations={plan.citations} />
      </Panel>
    </div>
  );
}
