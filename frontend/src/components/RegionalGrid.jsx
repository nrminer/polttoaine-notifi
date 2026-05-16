import React, { useState, useMemo } from "react";
import { MapPin, Clock, ArrowUpDown } from "lucide-react";
import { Card, CardLabel } from "./Card";

const ALL_CITIES = ["Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti"];

function FreshBadge({ ageHours }) {
  if (ageHours == null) return null;
  let color = "bg-signalDownBg text-signalDown";
  let label = `${Math.round(ageHours)} h`;
  if (ageHours < 1) {
    label = "juuri nyt";
    color = "bg-signalDownBg text-signalDown";
  } else if (ageHours < 6) {
    label = `${Math.round(ageHours)} h sitten`;
    color = "bg-signalDownBg text-signalDown";
  } else if (ageHours < 24) {
    label = `${Math.round(ageHours)} h sitten`;
    color = "bg-slate-100 text-secondary";
  } else {
    label = `${Math.round(ageHours)} h sitten`;
    color = "bg-amber-100 text-amber-800";
  }
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[10px] font-semibold px-1.5 py-0.5 ${color}`}>
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
          className={`px-2.5 h-7 font-mono text-[11px] font-semibold border transition-colors ${
            allSelected
              ? "bg-nordDark text-white border-nordDark"
              : "bg-white text-secondary border-line hover:border-ink"
          }`}
        >
          Kaikki
        </button>
        {ALL_CITIES.map((city) => (
          <button
            key={city}
            onClick={() => toggleCity(city)}
            className={`px-2.5 h-7 font-mono text-[11px] font-semibold border transition-colors ${
              selected.has(city)
                ? allSelected
                  ? "bg-white text-ink border-line hover:border-ink"
                  : "bg-brand/10 text-brand border-brand/40"
                : "bg-white text-muted border-line opacity-50 hover:opacity-80"
            }`}
          >
            {city}
          </button>
        ))}

        <button
          onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
          className="ml-auto flex items-center gap-1.5 px-3 h-7 font-mono text-[11px] font-semibold border border-line hover:bg-surface transition-colors whitespace-nowrap"
        >
          <ArrowUpDown size={11} />
          {sortDir === "asc" ? "Halvin ensin" : "Kallein ensin"}
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-line">
        {withData.map((row) => {
          const isCheapest = row.price === cheapestPrice;
          const meanDiff =
            row.mean != null && row.price != null ? row.mean - row.price : null;
          return (
            <div
              key={row.region}
              data-testid={`region-cell-${row.region}`}
              className={`bg-white p-4 hover:bg-surface transition-colors ${
                isCheapest ? "ring-2 ring-accent z-10" : ""
              }`}
            >
              <div className="flex items-baseline justify-between mb-1">
                <span className="font-semibold text-sm">{row.region}</span>
                {isCheapest && (
                  <span className="font-mono text-[9px] uppercase tracking-wider bg-accent text-ink px-1.5 py-0.5">
                    halvin
                  </span>
                )}
              </div>

              {/* Halvin */}
              <div className="font-mono tnum text-2xl font-bold">
                {row.price.toFixed(3)}
                <span className="text-secondary text-xs font-medium ml-1">€/L</span>
              </div>

              {/* Keskihinta + asemamäärä */}
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

              {/* Asema */}
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
