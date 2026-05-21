import React from "react";
import { Card, CardLabel } from "./Card";
import { Target, Award } from "lucide-react";

const METHOD_LABEL = {
  moving_average: "Liukuva ka.",
  linear_regression: "Lin. regr.",
  exp_smoothing: "Eksp. tas.",
  ai_llm: "AI / Claude",
  ensemble: "Ensemble",
};

const METHOD_COLOR = {
  moving_average: "#3B82F6",
  linear_regression: "#8B5CF6",
  exp_smoothing: "#EC4899",
  fundamental_anchor: "#F59E0B",
  ai_llm: "#10B981",
  ensemble: "#002FA7",
};

export default function AccuracyTracker({ data }) {
  const summary = data?.summary || {};
  const entries = Object.entries(summary).filter(([, s]) => s.n > 0);

  entries.sort(([, a], [, b]) => (a.mae ?? 99) - (b.mae ?? 99));

  return (
    <Card testId="accuracy-card" className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Target size={14} className="text-brand" strokeWidth={2.4} />
          <CardLabel>Tarkkuusseuranta</CardLabel>
        </div>
        <span className="font-mono text-[10px] text-muted uppercase tracking-wider">
          {data?.days ? `${data.days} pv` : "—"}
        </span>
      </div>

      {entries.length === 0 ? (
        <div className="font-mono text-xs text-secondary py-8 text-center border border-dashed border-line rounded-lg">
          Ei ennustehistoriaa vielä. Aja ennusteita useammalta päivältä,
          niin tarkkuus alkaa kertyä.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-line">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-surface text-left">
                <th className="font-mono text-[10px] uppercase text-muted py-2.5 px-3">Menetelmä</th>
                <th className="font-mono text-[10px] uppercase text-muted py-2.5 px-3 text-right">N</th>
                <th className="font-mono text-[10px] uppercase text-muted py-2.5 px-3 text-right">MAE €/L</th>
                <th className="font-mono text-[10px] uppercase text-muted py-2.5 px-3 text-right">≤1¢</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([key, s], idx) => (
                <tr
                  key={key}
                  data-testid={`accuracy-row-${key}`}
                  className={`border-b border-line last:border-b-0 transition-colors hover:bg-surface/60 ${
                    idx === 0 ? "bg-brand/5" : ""
                  }`}
                >
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: METHOD_COLOR[key] || "#64748B" }}
                      />
                      {idx === 0 && <Award size={12} className="text-accent shrink-0" />}
                      <span className="font-medium">{METHOD_LABEL[key] || key}</span>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-right font-mono tnum text-xs text-secondary">
                    {s.n}
                  </td>
                  <td className="py-3 px-3 text-right font-mono tnum font-bold">
                    <span
                      className="px-2 py-0.5 rounded-md text-xs"
                      style={{
                        backgroundColor: idx === 0 ? `${METHOD_COLOR[key] || "#002FA7"}18` : "transparent",
                        color: idx === 0 ? METHOD_COLOR[key] || "#002FA7" : undefined,
                      }}
                    >
                      {s.mae?.toFixed(4)}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right font-mono tnum text-xs">
                    {s.within_1c_pct != null && (
                      <span className={`px-2 py-0.5 rounded-md ${
                        s.within_1c_pct >= 50 ? "bg-emerald-100 text-emerald-700" : "text-secondary"
                      }`}>
                        {s.within_1c_pct.toFixed(0)}%
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
