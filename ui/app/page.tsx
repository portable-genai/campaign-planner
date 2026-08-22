"use client";

import { useEffect, useState } from "react";
import { PlanView } from "@/components/PlanView";
import { api, API_BASE, ApiError, setDevPersona } from "@/lib/api";
import type { Health, Market, Pacing, Persona, Plan, Vertical } from "@/lib/types";

const IS_EMBED = process.env.NEXT_PUBLIC_EMBED === "1";

const MARKETS: { value: Market; label: string }[] = [
  { value: "JP", label: "Japan (asia-northeast1)" },
  { value: "AU", label: "Australia (australia-southeast1)" },
  { value: "SG", label: "Singapore (asia-southeast1)" },
];
const VERTICALS: { value: Vertical; label: string }[] = [
  { value: "banking", label: "Banking" },
  { value: "online_retail", label: "Online retail" },
];
const PACINGS: { value: Pacing; label: string }[] = [
  { value: "even", label: "Even" },
  { value: "front_loaded", label: "Front-loaded" },
  { value: "back_loaded", label: "Back-loaded" },
];

export default function Page() {
  const [objective, setObjective] = useState("savings account acquisition");
  const [market, setMarket] = useState<Market>("SG");
  const [vertical, setVertical] = useState<Vertical>("banking");
  const [budget, setBudget] = useState("120000");
  const [pacing, setPacing] = useState<Pacing>("even");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersona, setSelectedPersona] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const status = await api.healthz();
      if (cancelled) return;
      setHealth(status);
      // The persona picker is a LOCAL-profile convenience only: secure profiles resolve
      // identity server-side from the IAP assertion, never from a client hint.
      if (!status || status.profile !== "local") return;
      try {
        const list = await api.listPersonas();
        if (cancelled || list.length === 0) return;
        setPersonas(list);
        setSelectedPersona(list[0].id);
        setDevPersona(list[0].id);
      } catch {
        // Persona picker is dev-only convenience; ignore lookup failures.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function onPersonaChange(id: string) {
    setSelectedPersona(id);
    setDevPersona(id);
  }

  async function onBuild() {
    setLoading(true);
    setError(null);
    setPlan(null);
    try {
      const result = await api.buildPlan({
        objective,
        market,
        vertical,
        total_budget: Number(budget) || 0,
        start_date: "2026-07-01",
        end_date: "2026-07-28",
        pacing,
      });
      setPlan(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-6xl gap-6 p-6">
      <aside className="w-80 shrink-0">
        {/* EMBED mode: the host page owns the chrome, so drop our own title block. */}
        {!IS_EMBED ? (
          <>
            <h1 className="text-base font-semibold">D2 Campaign Planner</h1>
            <p className="mb-4 text-xs text-ink-500">
              Cited campaign plans (audience, channel-mix budget allocation, reach /
              frequency, pacing), generic across banking and online retail and the JP/AU/SG
              markets.
            </p>
          </>
        ) : null}

        {personas.length > 0 ? (
          <div className="mb-3 rounded-xl border border-ink-200 bg-white p-4 shadow-panel">
            <label className="mb-1 block text-xs font-semibold text-ink-600">
              Demo identity
            </label>
            <select
              className="w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
              value={selectedPersona}
              onChange={(e) => onPersonaChange(e.target.value)}
            >
              {personas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.subject} · {p.tenant}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-ink-500">
              Local profile only: selects the seeded persona sent as X-Dev-Persona.
            </p>
          </div>
        ) : null}

        <div className="rounded-xl border border-ink-200 bg-white p-4 shadow-panel">
          <label className="mb-1 block text-xs font-semibold text-ink-600">Objective</label>
          <input
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
          />

          <label className="mb-1 block text-xs font-semibold text-ink-600">Market</label>
          <select
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={market}
            onChange={(e) => setMarket(e.target.value as Market)}
          >
            {MARKETS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>

          <label className="mb-1 block text-xs font-semibold text-ink-600">Vertical</label>
          <select
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={vertical}
            onChange={(e) => setVertical(e.target.value as Vertical)}
          >
            {VERTICALS.map((v) => (
              <option key={v.value} value={v.value}>
                {v.label}
              </option>
            ))}
          </select>

          <label className="mb-1 block text-xs font-semibold text-ink-600">
            Total budget
          </label>
          <input
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={budget}
            inputMode="numeric"
            onChange={(e) => setBudget(e.target.value)}
          />

          <label className="mb-1 block text-xs font-semibold text-ink-600">Pacing</label>
          <select
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={pacing}
            onChange={(e) => setPacing(e.target.value as Pacing)}
          >
            {PACINGS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>

          <button
            onClick={onBuild}
            disabled={loading || !objective.trim()}
            className="w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {loading ? "Planning…" : "Build cited plan"}
          </button>
        </div>

        <div className="mt-3 rounded-xl border border-ink-200 bg-white p-3 text-xs text-ink-500 shadow-panel">
          <div>
            API <span className="font-mono">{API_BASE}</span>
          </div>
          {health ? (
            <div className="mt-1">
              profile <b className="text-ink-700">{health.profile}</b> · status{" "}
              <b className="text-ink-700">{health.status}</b>
            </div>
          ) : (
            <div className="mt-1 text-amber-700">backend not reachable (start the API)</div>
          )}
        </div>
      </aside>

      <section className="min-w-0 flex-1">
        {error ? (
          <div className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}
        {!plan && !error ? (
          <div className="rounded-xl border border-dashed border-ink-200 bg-white p-10 text-center text-sm text-ink-400">
            Configure an objective, market, vertical and budget, then build a cited plan.
          </div>
        ) : null}
        {plan ? <PlanView plan={plan} /> : null}
      </section>
    </main>
  );
}
