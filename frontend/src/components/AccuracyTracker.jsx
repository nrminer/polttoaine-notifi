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

export default function AccuracyTracker({ data }) {
  const summary = data?.summary || {};
  const entries = Object.entries(summary).filter(([, s]) => s.n > 0);

  // sort by MAE asc, ensemble pinned at top after sort
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
        <div className="font-mono text-xs text-secondary py-6 text-center">
          Ei ennustehistoriaa vielä. Aja ennusteita useamman päivän ajalta,
          niin tarkkuus alkaa kertyä.
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              <th className="font-mono text-[10px] uppercase text-muted py-2">Menetelmä</th>
              <th className="font-mono text-[10px] uppercase text-muted py-2 text-right">N</th>
              <th className="font-mono text-[10px] uppercase text-muted py-2 text-right">MAE €/L</th>
              <th className="font-mono text-[10px] uppercase text-muted py-2 text-right">≤1¢</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, s], idx) => (
              <tr
                key={key}
                data-testid={`accuracy-row-${key}`}
                className="border-b border-line/60 hover:bg-surface/60"
              >
                <td className="py-2.5 flex items-center gap-2">
                  {idx === 0 && <Award size={12} className="text-accent" />}
                  <span className="font-medium">{METHOD_LABEL[key] || key}</span>
                </td>
                <td className="py-2.5 text-right font-mono tnum text-xs text-secondary">
                  {s.n}
                </td>
                <td className="py-2.5 text-right font-mono tnum font-bold">
                  {s.mae?.toFixed(4)}
                </td>
                <td className="py-2.5 text-right font-mono tnum text-xs">
                  {s.within_1c_pct?.toFixed(0)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
