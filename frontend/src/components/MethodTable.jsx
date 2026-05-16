import React from "react";
import { Sparkles, Activity, TrendingUp, Brain, Calculator } from "lucide-react";
import { Card, CardLabel, DeltaBadge } from "./Card";
import { fmtPrice, fmtDelta } from "../lib/utils";
import { formatModelName } from "../lib/modelName";

const META = {
  moving_average: { label: "Liukuva keskiarvo", Icon: Activity, sub: "7 pv" },
  linear_regression: { label: "Lineaarinen regressio", Icon: TrendingUp, sub: "30 pv" },
  exp_smoothing: { label: "Eksp. tasoitus", Icon: Sparkles, sub: "Holt α=0.4" },
  ai_llm: { Icon: Brain },  // label/sub built dynamically from model id
};

function aiLabelFor(model) {
  // "Claude Opus 4.7" → label "AI / Claude Opus", sub "4.7"
  const full = formatModelName(model); // "Claude Opus 4.7"
  const parts = full.split(" ");
  if (parts.length >= 3) {
    return { label: `AI / ${parts[0]} ${parts[1]}`, sub: parts.slice(2).join(" ") };
  }
  return { label: `AI / ${full}`, sub: "" };
}

export default function MethodTable({ result }) {
  const methods = result?.methods || {};
  const current = result?.current_price;
  return (
    <Card span="" testId="method-comparison-card" className="p-6">
      <div className="flex items-center justify-between mb-2">
        <CardLabel>Menetelmävertailu — huominen</CardLabel>
        <Calculator size={14} strokeWidth={2.4} className="text-secondary" />
      </div>
      {result?.data_sources && (
        <p className="text-[10px] text-muted font-mono mb-4" data-testid="method-data-sources">
          Data: Tilastokeskus {result.data_sources.statfin_monthly_points} kk + tracker {result.data_sources.tracker_captures} havaintoa · {result.data_sources.combined_points} pistettä yhteensä
        </p>
      )}

      <div className="space-y-3">
        {Object.entries(META).map(([key, m]) => {
          const row = methods[key] || {};
          const v = row.value;
          const delta = v != null && current != null ? v - current : null;
          const lo = row.confidence_low;
          const hi = row.confidence_high;
          // resolve label/sub dynamically for ai_llm
          const dyn = key === "ai_llm" ? aiLabelFor(row.model) : null;
          const label = dyn?.label ?? m.label;
          const sub = dyn?.sub ?? m.sub;
          return (
            <div
              key={key}
              data-testid={`method-row-${key}`}
              className="flex items-start justify-between gap-3 py-2 border-b border-line last:border-b-0"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <m.Icon size={14} strokeWidth={2.4} className="text-brand" />
                  <span className="font-semibold text-sm">{label}</span>
                  <span className="font-mono text-[10px] text-muted uppercase tracking-wider">
                    {sub}
                  </span>
                </div>
                <p className="text-xs text-secondary mt-1 leading-relaxed line-clamp-2">
                  {row.explanation || "—"}
                </p>
                {lo != null && hi != null && (
                  <p className="font-mono text-[10px] text-muted mt-1">
                    luottamus {fmtPrice(lo)} … {fmtPrice(hi)} €/L
                  </p>
                )}
              </div>
              <div className="text-right shrink-0">
                <div className="font-mono tnum text-xl font-bold">
                  {v != null ? fmtPrice(v) : "—"}
                </div>
                <DeltaBadge delta={delta} />
              </div>
            </div>
          );
        })}
      </div>

      {result?.ensemble && (
        <div className="mt-4 pt-4 border-t-2 border-nordDark">
          <div className="flex justify-between items-center">
            <div>
              <CardLabel className="text-ink">Ensemble (painotettu)</CardLabel>
              <p className="text-xs text-secondary mt-1">
                {result.ensemble.n_methods} menetelmää · hajonta{" "}
                {fmtPrice(result.ensemble.spread)} €/L
              </p>
            </div>
            <div className="text-right">
              <div className="font-mono tnum text-2xl font-bold text-brand">
                {fmtPrice(result.ensemble.value)}
                <span className="text-secondary font-medium text-sm ml-1">€/L</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
