import React from "react";
import { Waves, Activity, TrendingUp, MessageSquareText, Calculator, Anchor } from "lucide-react";
import { Card, CardLabel, DeltaBadge } from "./Card";
import { fmtPrice } from "../lib/utils";
import { formatModelName } from "../lib/modelName";

const METHOD_COLORS = {
  moving_average: "#3B82F6",
  linear_regression: "#8B5CF6",
  exp_smoothing: "#EC4899",
  fundamental_anchor: "#F59E0B",
  ai_llm: "#10B981",
};

const META = {
  moving_average: { label: "Liukuva keskiarvo", Icon: Activity, sub: "7 pv" },
  linear_regression: { label: "Lineaarinen regressio", Icon: TrendingUp, sub: "≤14 pv painotettu" },
  exp_smoothing: { label: "Eksp. tasoitus", Icon: Waves, sub: "Holt α=0.4" },
  fundamental_anchor: { label: "Fundamenttiankkuri", Icon: Anchor, sub: "Brent+FX" },
  ai_llm: { Icon: MessageSquareText },
};

function aiLabelFor(model) {
  const full = formatModelName(model);
  if (!full) return { label: "Uutis- ja malliarvio", sub: "ei ajettu" };
  return { label: "Uutis- ja malliarvio", sub: full };
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
          Data: vain livenä mitatut havainnot — {result.data_sources.tracker_captures} mittausta · {result.data_sources.combined_points} päiväpistettä (kerätty tästä päivästä alkaen)
        </p>
      )}

      <div className="space-y-2.5">
        {Object.entries(META).map(([key, m]) => {
          const row = methods[key] || {};
          const v = row.value;
          const delta = v != null && current != null ? v - current : null;
          const lo = row.confidence_low;
          const hi = row.confidence_high;
          const dyn = key === "ai_llm" ? aiLabelFor(row.model) : null;
          const label = dyn?.label ?? m.label;
          const sub = dyn?.sub ?? m.sub;
          const color = METHOD_COLORS[key] || "#64748B";
          const weight = result?.ensemble?.weights?.[key];
          const weightPct = weight != null ? Math.max(0, Math.min(100, weight * 100)) : null;
          return (
            <div
              key={key}
              data-testid={`method-row-${key}`}
              className="flex items-start justify-between gap-3 py-2.5 border-b border-line last:border-b-0"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <m.Icon size={14} strokeWidth={2.4} style={{ color }} className="shrink-0" />
                  <span className="font-semibold text-sm">{label}</span>
                  <span className="font-mono text-[11px] text-muted uppercase tracking-wider">
                    {sub}
                  </span>
                </div>
                <p className="text-xs text-secondary mt-1 leading-relaxed line-clamp-2 pl-[22px]">
                  {row.explanation || "—"}
                </p>
                {lo != null && hi != null && (
                  <p className="font-mono text-[11px] text-muted mt-1 pl-[22px]">
                    mallin väli {fmtPrice(lo)} … {fmtPrice(hi)} €/L
                  </p>
                )}
                {weightPct != null && (
                  <div
                    className="pl-[22px] mt-2 flex items-center gap-2"
                    title={`Yhdistelmäpaino ${weightPct.toFixed(0)} %`}
                    data-testid={`method-weight-${key}`}
                  >
                    <div className="flex-1 h-1.5 rounded-full bg-line overflow-hidden max-w-[180px]">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${weightPct}%`, backgroundColor: color }}
                      />
                    </div>
                    <span className="font-mono text-[11px] tnum text-secondary tabular-nums w-9 text-right">
                      {weightPct.toFixed(0)}%
                    </span>
                  </div>
                )}
              </div>
              <div className="text-right shrink-0">
                <div className="font-mono tnum text-xl font-bold" style={{ color: v != null ? color : undefined }}>
                  {v != null ? fmtPrice(v) : "—"}
                </div>
                <DeltaBadge delta={delta} />
              </div>
            </div>
          );
        })}
      </div>

      {result?.ensemble && (
        <div className="mt-4 pt-4 border-t-2 border-brand/30 bg-brand/5 -mx-6 px-6 -mb-6 pb-6 rounded-b-xl">
          <div className="flex justify-between items-center">
            <div>
              <CardLabel className="text-brand">Ensemble (painotettu)</CardLabel>
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
