import React from "react";
import { MapPin, Clock } from "lucide-react";
import { Card, CardLabel } from "./Card";

function FreshBadge({ ageHours }) {
  if (ageHours == null) return null;
  let color = "bg-signalDownBg text-signalDown";
  let label = `${Math.round(ageHours)} h`;
  if (ageHours < 1) {
    label = "juuri nyt";
  } else if (ageHours < 6) {
    label = `${Math.round(ageHours)} h sitten`;
  } else if (ageHours < 24) {
    label = `${Math.round(ageHours)} h sitten`;
    color = "bg-slate-100 text-secondary";
  } else {
    color = "bg-amber-100 text-amber-800";
    label = `${Math.round(ageHours)} h sitten`;
  }
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-1.5 py-0.5 ${color}`}>
      <Clock size={9} strokeWidth={2.6} />
      {label}
    </span>
  );
}

export default function RegionalGrid({ data, fuel }) {
  const rows = data?.rows || [];
  const maxAge = data?.max_age_hours || 24;

  // pyörimme vain ne joilla on dataa otsikon alle, sitten ei-dataa loppuun
  const withData = rows.filter((r) => r.price != null);
  const noData = rows.filter((r) => r.price == null);

  return (
    <Card testId="regional-grid-card" className="p-6">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <MapPin size={14} className="text-brand" strokeWidth={2.4} />
          <CardLabel>Alueellinen vertailu</CardLabel>
        </div>
        <span className="font-mono text-[10px] text-muted uppercase tracking-wider">
          {fuel}
        </span>
      </div>
      <div className="text-[11px] text-muted font-mono mb-4">
        live · halvin asema / kaupunki · ≤ {maxAge}h tuoreutta
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-line">
        {withData.map((row, idx) => (
          <div
            key={row.region}
            data-testid={`region-cell-${row.region}`}
            className={`bg-white p-4 hover:bg-surface transition-colors ${
              idx === 0 ? "ring-2 ring-accent z-10" : ""
            }`}
          >
            <div className="flex items-baseline justify-between mb-1">
              <span className="font-semibold text-sm">{row.region}</span>
              {idx === 0 && (
                <span className="font-mono text-[9px] uppercase tracking-wider bg-accent text-ink px-1.5 py-0.5">
                  halvin
                </span>
              )}
            </div>
            <div className="font-mono tnum text-2xl font-bold">
              {row.price.toFixed(3)}
              <span className="text-secondary text-xs font-medium ml-1">€/L</span>
            </div>
            <div
              className="text-[11px] text-secondary mt-1 line-clamp-1"
              title={row.station || ""}
              data-testid={`region-station-${row.region}`}
            >
              {row.station || "—"}
            </div>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <FreshBadge ageHours={row.age_hours} />
              <span className="font-mono text-[9px] text-muted uppercase tracking-wider">
                {row.source}
              </span>
            </div>
          </div>
        ))}

        {noData.map((row) => (
          <div
            key={row.region}
            data-testid={`region-cell-${row.region}`}
            className="bg-white p-4 opacity-60"
          >
            <div className="flex items-baseline justify-between mb-1">
              <span className="font-semibold text-sm">{row.region}</span>
            </div>
            <div className="font-mono tnum text-lg font-bold text-muted">—</div>
            <div className="text-[11px] text-muted mt-1">ei tuoretta dataa</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
