import React from "react";
import { MapPin } from "lucide-react";
import { Card, CardLabel, DeltaBadge } from "./Card";

export default function RegionalGrid({ data, fuel }) {
  const rows = data?.rows || [];

  return (
    <Card testId="regional-grid-card" className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <MapPin size={14} className="text-brand" strokeWidth={2.4} />
          <CardLabel>Alueellinen vertailu</CardLabel>
        </div>
        <span className="font-mono text-[10px] text-muted uppercase tracking-wider">
          {fuel}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-line">
        {rows.map((row, idx) => (
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
              {row.price?.toFixed(3)}
              <span className="text-secondary text-xs font-medium ml-1">€/L</span>
            </div>
            <div className="mt-1">
              <DeltaBadge delta={row.delta} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
