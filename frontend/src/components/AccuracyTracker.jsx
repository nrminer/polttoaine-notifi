import React, { useState } from "react";
import { Card, CardLabel } from "./Card";
import { Target, ChevronDown, ChevronUp } from "lucide-react";

const METHOD_LABEL = {
  moving_average: "Liukuva keskiarvo",
  linear_regression: "Lineaarinen regressio",
  exp_smoothing: "Eksponentiaalinen tasoitus",
  fundamental_anchor: "Fundamenttiankkuri",
  ai_llm: "Uutis- ja malliarvio",
  ensemble: "Yhdistelmä",
};

export default function AccuracyTracker({ data }) {
  const [showDetails, setShowDetails] = useState(false);
  const summary = data?.summary || {};
  const ensembleStats = summary.ensemble;

  if (!ensembleStats || ensembleStats.n === 0) {
    return (
      <Card testId="accuracy-card" className="p-6">
        <div className="flex items-center gap-2 mb-4">
          <Target size={14} className="text-brand" strokeWidth={2.4} />
          <CardLabel>Toteutunut ennustevirhe</CardLabel>
        </div>
        <div className="font-mono text-xs text-secondary py-8 text-center border border-dashed border-line rounded-lg">
          Ei vielä tarpeeksi toteutuneita vertailuja virheen laskemiseen.
        </div>
      </Card>
    );
  }

  const maeCents = (ensembleStats.mae * 100).toFixed(1);
  const hitRate = ensembleStats.within_2c_pct?.toFixed(0) || "—";
  const days = data?.days || "—";

  const entries = Object.entries(summary).filter(([, s]) => s.n > 0);
  entries.sort(([, a], [, b]) => (a.mae ?? 99) - (b.mae ?? 99));

  return (
    <Card testId="accuracy-card" className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Target size={14} className="text-brand" strokeWidth={2.4} />
          <CardLabel>Toteutunut ennustevirhe</CardLabel>
        </div>
        <span className="font-mono text-[10px] text-muted uppercase tracking-wider">
          {days} pv
        </span>
      </div>

      <div className="text-center mb-4 pb-4 border-b border-line">
        <div className="mb-3">
          <div className="text-5xl font-bold tnum text-brand mb-2" data-testid="accuracy-mae-cents">
            ±{maeCents}¢
          </div>
          <div className="text-sm text-secondary mb-1">Keskivirhe</div>
        </div>

        <div className="mb-4">
          <div className="text-3xl font-bold tnum text-accent mb-1" data-testid="accuracy-hit-rate">
            {hitRate}%
          </div>
          <div className="text-sm text-secondary">Vertailuja ±2¢ sisällä</div>
        </div>

        <div className="text-sm text-secondary leading-relaxed max-w-md mx-auto">
          Ennuste on tähän mennessä poikennut keskimäärin <span className="font-semibold text-ink">±{maeCents} senttiä</span> toteutuneesta hinnasta.
          <span className="font-semibold text-ink"> {hitRate}%</span> vertailuista on kahden sentin sisällä.
        </div>
      </div>

      <button
        onClick={() => setShowDetails(!showDetails)}
        className="w-full flex items-center justify-center gap-2 py-2 text-xs font-medium text-brand hover:text-accent transition-colors"
        data-testid="accuracy-toggle-details"
      >
        {showDetails ? (
          <>
            Piilota yksityiskohdat <ChevronUp size={14} />
          </>
        ) : (
          <>
            Näytä yksityiskohdat <ChevronDown size={14} />
          </>
        )}
      </button>

      {showDetails && (
        <div className="mt-4 space-y-3">
          <div className="text-xs text-secondary leading-relaxed p-4 bg-surface rounded-lg border border-line">
            <p className="mb-2">
              <span className="font-semibold text-ink">Keskivirhe</span> mittaa, kuinka paljon ennuste keskimäärin poikkeaa todellisesta hinnasta.
              Pienempi luku on parempi.
            </p>
            <p>
              <span className="font-semibold text-ink">Vertailuja ±2¢ sisällä</span> kertoo, kuinka usein ennuste on alle kahden sentin päässä toteutuneesta hinnasta.
            </p>
          </div>

          <div className="overflow-hidden rounded-lg border border-line">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-surface text-left">
                  <th className="font-mono text-[10px] uppercase text-muted py-2.5 px-3">Menetelmä</th>
                  <th className="font-mono text-[10px] uppercase text-muted py-2.5 px-3 text-right">Keskivirhe</th>
                  <th className="font-mono text-[10px] uppercase text-muted py-2.5 px-3 text-right">≤2¢ vertailut</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(([key, s]) => (
                  <tr
                    key={key}
                    data-testid={`accuracy-row-${key}`}
                    className="border-b border-line last:border-b-0 transition-colors hover:bg-surface/60"
                  >
                    <td className="py-3 px-3">
                      <span className="text-xs text-ink">{METHOD_LABEL[key] || key}</span>
                    </td>
                    <td className="py-3 px-3 text-right font-mono tnum text-xs font-medium">
                      ±{(s.mae * 100).toFixed(1)}¢
                    </td>
                    <td className="py-3 px-3 text-right font-mono tnum text-xs text-secondary">
                      {s.within_2c_pct != null ? `${s.within_2c_pct.toFixed(0)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}
