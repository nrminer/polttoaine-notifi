import React from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { fmtDateFi } from "../lib/utils";

function TooltipBody({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const human = (() => {
    if (!label) return "";
    const [d, h] = String(label).split(" ");
    return fmtDateFi(d) + (h ? ` · klo ${h}:00` : "");
  })();
  return (
    <div 
      role="tooltip"
      aria-live="polite"
      className="bg-white border border-line rounded-lg shadow-lg px-3 py-2.5 font-mono text-xs min-w-[160px]"
    >
      <div className="text-secondary mb-1.5 text-[10px] uppercase tracking-wider">{human}</div>
      {payload.map(
        (p) =>
          p.value != null && (
            <div key={p.dataKey} className="flex justify-between gap-4 text-ink py-0.5">
              <span style={{ color: p.color }}>{p.name}</span>
              <span className="tnum font-semibold">
                {Array.isArray(p.value)
                  ? `${p.value[0].toFixed(3)} – ${p.value[1].toFixed(3)} €/L`
                  : `${p.value.toFixed(3)} €/L`}
              </span>
            </div>
          )
      )}
    </div>
  );
}

export default function TrackingChart({
  rows = [],
  tomorrow,
  city = "Suomi",
  height = 320,
}) {
  const isCity = city && city !== "Suomi";

  const data = rows.map((r) => {
    const hour = r.hour ?? 20;
    const slot = `${r.date} ${String(hour).padStart(2, "0")}`;
    if (isCity) {
      const c = (r.by_city && r.by_city[city]) || {};
      return {
        slot,
        date: r.date,
        hour,
        cheapest: c.cheapest ?? null,
        average: c.average ?? null,
      };
    }
    const lo = r.prediction_full?.ensemble?.confidence_low ?? null;
    const hi = r.prediction_full?.ensemble?.confidence_high ?? null;
    return {
      slot,
      date: r.date,
      hour,
      actual: r.actual_cheapest,
      predicted: r.predicted_cheapest_for_today,
      band: lo != null && hi != null ? [lo, hi] : null,
    };
  });

  if (!isCity && rows.length && tomorrow?.date && tomorrow?.value != null) {
    const tomorrowConfidence = tomorrow.confidence_range || {};
    const lo = tomorrowConfidence.low ?? null;
    const hi = tomorrowConfidence.high ?? null;
    data.push({
      slot: `${tomorrow.date} 14`,
      date: tomorrow.date,
      hour: 14,
      tomorrow: tomorrow.value,
      band: lo != null && hi != null ? [lo, hi] : null,
    });
  }

  const prices = data
    .flatMap((d) =>
      isCity
        ? [d.cheapest, d.average]
        : [d.actual, d.predicted, d.tomorrow, ...(d.band || [])]
    )
    .filter((v) => v !== null && v !== undefined);

  if (prices.length === 0) {
    return (
      <div
        className="font-mono text-xs text-secondary py-12 text-center border border-dashed border-line rounded-lg"
        style={{ height }}
        data-testid="tracking-chart-empty"
      >
        {isCity
          ? `Ei vielä ${city}-dataa. Kaupunkikohtainen historia kertyy klo 14 ja 21 mittauksista.`
          : "Ei vielä dataa. Hinnat mitataan automaattisesti klo 14 ja 21 (Helsinki) — ensimmäiset pisteet ilmestyvät tähän seuraavan mittauksen jälkeen."}
      </div>
    );
  }
  const min = Math.min(...prices) - 0.02;
  const max = Math.max(...prices) + 0.02;

  // Determine confidence band color based on data quality
  const getConfidenceBandColor = () => {
    const totalPoints = rows.length;
    if (totalPoints >= 14) return { fill: "#10B981", opacity: 0.15 }; // green (rich)
    if (totalPoints >= 7) return { fill: "#F59E0B", opacity: 0.15 }; // yellow (sufficient)
    return { fill: "#EF4444", opacity: 0.15 }; // red (thin)
  };
  const confidenceBandStyle = getConfidenceBandColor();

  return (
    <div className="w-full" style={{ height }} data-testid="tracking-chart">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, right: 16, left: 8, bottom: 8 }}>
          <CartesianGrid stroke="#E2E8F0" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="slot"
            tickFormatter={(s) => {
              if (!s) return "";
              const [d, h] = s.split(" ");
              const [, m, day] = d.split("-");
              return `${parseInt(day)}.${parseInt(m)} ${h}:00`;
            }}
            tick={{ fontSize: 11, fill: "#64748B" }}
            tickLine={false}
            axisLine={{ stroke: "#CBD5E1" }}
            minTickGap={24}
          />
          <YAxis
            domain={[min, max]}
            tickFormatter={(v) => v.toFixed(2)}
            tick={{ fontSize: 11, fill: "#64748B" }}
            tickLine={false}
            axisLine={{ stroke: "#CBD5E1" }}
            width={50}
          />
          <Tooltip content={<TooltipBody />} />
          <Legend
            verticalAlign="top"
            wrapperStyle={{
              fontSize: "11px",
              fontFamily: "JetBrains Mono",
              paddingBottom: 10,
            }}
          />

          {isCity ? (
            <>
              <Line
                type="monotone"
                dataKey="cheapest"
                name={`${city} · halvin`}
                stroke="#002FA7"
                strokeWidth={3}
                dot={{ r: 4, fill: "#002FA7", stroke: "#fff", strokeWidth: 1.5 }}
                activeDot={{ r: 6 }}
                connectNulls
                isAnimationActive
              />
              <Line
                type="monotone"
                dataKey="average"
                name={`${city} · keskihinta`}
                stroke="#F59E0B"
                strokeWidth={2.5}
                strokeDasharray="5 4"
                dot={{ r: 3, fill: "#F59E0B", stroke: "#fff", strokeWidth: 1 }}
                connectNulls
                isAnimationActive
              />
            </>
          ) : (
            <>
              <Area
                type="monotone"
                dataKey="band"
                name="Luottamusväli"
                stroke="none"
                fill={confidenceBandStyle.fill}
                fillOpacity={confidenceBandStyle.opacity}
                connectNulls
                isAnimationActive
              />
              <Line
                type="monotone"
                dataKey="actual"
                name="Toteutunut halvin"
                stroke="#002FA7"
                strokeWidth={3}
                dot={{ r: 4, fill: "#002FA7", stroke: "#fff", strokeWidth: 1.5 }}
                activeDot={{ r: 6 }}
                connectNulls
                isAnimationActive
              />
              <Scatter
                name="Edellisen päivän ennuste"
                dataKey="predicted"
                fill="#94A3B8"
                shape="cross"
              />
              <Line
                type="monotone"
                dataKey="tomorrow"
                name="Huomisen ennuste"
                stroke="#FDE047"
                strokeWidth={2.5}
                strokeDasharray="6 4"
                dot={{ r: 6, fill: "#FDE047", stroke: "#0F172A", strokeWidth: 2 }}
                connectNulls
                isAnimationActive
              />
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
