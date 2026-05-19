import React, { useState, useMemo } from "react";
import { MapPin, Clock, ArrowUpDown } from "lucide-react";
import { Card, CardLabel } from "./Card";

const ALL_CITIES = ["Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti"];

function FreshBadge({ ageHours }) {
  if (ageHours == null) return null;
  let color, label;
  if (ageHours < 1) {
    label = "juuri nyt";
    color = "bg-emerald-100 text-emerald-700";
  } else if (ageHours < 6) {
    label = `${Math.round(ageHours)} h sitten`;
    color = "bg-emerald-100 text-emerald-700";
  } else if (ageHours < 24) {
    label = `${Math.round(ageHours)} h sitten`;
    color = "bg-surface text-secondary border border-line";
  } else {
    label = `${Math.round(ageHours)} h sitten`;
    color = "bg-amber-100 text-amber-700";
  }
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${color}`}>
      <Clock size={9} strokeWidth={2.6} />
      {label}
    </span>
  );
}

export default function RegionalGrid({ data, fuel, cityData }) {
  const rows = data?.rows || [];
  const maxAge = data?.max_age_hours || 24;

  const [sortDir, setSortDir] = useState("asc");
  const [selected, setSelected] = useState(() => new Set(ALL_CITIES));

  const toggleCity = (city) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(city)) {
        if (next.size === 1) return prev;
        next.delete(city);
      } else {
        next.add(city);
      }
      return next;
    });
  };

  const allSelected = selected.size === ALL_CITIES.length;

  const enriched = useMemo(() => {
    return rows.map((row) => ({
      ...row,
      mean: cityData?.[row.region]?.mean ?? null,
      count: cityData?.[row.region]?.count ?? null,
    }));
  }, [rows, cityData]);

  const filtered = useMemo(() => {
    let r = enriched.filter((row) => selected.has(row.region));
    r.sort((a, b) => {
      if (a.price == null && b.price == null) return 0;
      if (a.price == null) return 1;
      if (b.price == null) return -1;
      return sortDir === "asc" ? a.price - b.price : b.price - a.price;
    });
    return r;
  }, [enriched, selected, sortDir]);

  const withData = filtered.filter((r) => r.price != null);
  const noData = filtered.filter((r) => r.price == null);
  const cheapestPrice = withData[0]?.price;

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
        live · halvin asema + kaupungin keskihinta · ≤ {maxAge}h tuoreutta
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 mb-4 pb-4 border-b border-line">
        <button
          onClick={() => setSelected(new Set(ALL_CITIES))}
          className={`px-2.5 h-7 font-mono text-[11px] font-semibold rounded-md border transition-all duration-200 ${
            allSelected
              ? "bg-brand text-white border-brand shadow-sm"
              : "bg-transparent text-secondary border-line hover:border-brand/50 hover:text-ink"
          }`}
        >
          Kaikki
        </button>
        {ALL_CITIES.map((city) => (
          <button
            key={city}
            onClick={() => toggleCity(city)}
            className={`px-2.5 h-7 font-mono text-[11px] font-semibold rounded-md border transition-all duration-200 ${
              selected.has(city)
                ? allSelected
                  ? "bg-transparent text-secondary border-line hover:border-brand/50"
                  : "bg-brand/10 text-brand border-brand/40"
                : "bg-transparent text-muted border-line opacity-50 hover:opacity-80"
            }`}
          >
            {city}
          </button>
        ))}

        <button
          onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
          className="ml-auto flex items-center gap-1.5 px-3 h-7 font-mono text-[11px] font-semibold rounded-md border border-line hover:bg-surface transition-colors whitespace-nowrap"
        >
          <ArrowUpDown size={11} />
          {sortDir === "asc" ? "Halvin ensin" : "Kallein ensin"}
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {withData.map((row) => {
          const isCheapest = row.price === cheapestPrice;
          const meanDiff =
            row.mean != null && row.price != null ? row.mean - row.price : null;
          return (
            <div
              key={row.region}
              data-testid={`region-cell-${row.region}`}
              className={`rounded-xl p-4 border transition-all duration-200 hover:shadow-card-hover ${
                isCheapest
                  ? "border-accent bg-accent/5 ring-1 ring-accent/30"
                  : "border-line bg-surface hover:border-brand/20"
              }`}
            >
              <div className="flex items-baseline justify-between mb-1.5">
                <span className="font-semibold text-sm">{row.region}</span>
                {isCheapest && (
                  <span className="font-mono text-[9px] uppercase tracking-wider bg-accent text-slate-900 px-1.5 py-0.5 rounded-full font-bold">
                    halvin
                  </span>
                )}
              </div>

              <div className="font-mono tnum text-2xl font-bold">
                {row.price.toFixed(3)}
                <span className="text-secondary text-xs font-medium ml-1">€/L</span>
              </div>

              {row.mean != null && (
                <div className="mt-0.5 flex items-center gap-1.5 flex-wrap">
                  <span className="font-mono text-[10px] text-muted">
                    ka. {row.mean.toFixed(3)} €/L
                  </span>
                  {meanDiff != null && meanDiff > 0.002 && (
                    <span className="font-mono text-[10px] text-slate-400">
                      (+{meanDiff.toFixed(3)})
                    </span>
                  )}
                  {row.count != null && (
                    <span className="font-mono text-[10px] text-muted">
                      · {row.count} as.
                    </span>
                  )}
                </div>
              )}

              <div
                className="text-[11px] text-secondary mt-1.5 line-clamp-1"
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
          );
        })}

        {noData.map((row) => (
          <div
            key={row.region}
            data-testid={`region-cell-${row.region}`}
            className="rounded-xl p-4 border border-line bg-surface opacity-50"
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
