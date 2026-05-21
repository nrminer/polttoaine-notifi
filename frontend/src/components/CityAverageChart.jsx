import React from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { fmtDateFi } from "../lib/utils";

const CITIES = ["Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti"];
const CITY_COLOR = {
  Helsinki: "#3B82F6",
  Espoo: "#8B5CF6",
  Vantaa: "#06B6D4",
  Tampere: "#EC4899",
  Turku: "#22C55E",
  Lahti: "#F59E0B",
};
const ALL_COLOR = "#002FA7";
const PROJ_COLOR = "#FDE047";

function TooltipBody({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const human = (() => {
    if (!label) return "";
    const [d, h] = String(label).split(" ");
    return fmtDateFi(d) + (h ? ` · klo ${h}:00` : "");
  })();
  return (
    <div className="bg-white border border-line rounded-lg shadow-lg px-3 py-2.5 font-mono text-xs min-w-[180px]">
      <div className="text-secondary mb-1.5 text-[10px] uppercase tracking-wider">{human}</div>
      {payload.map(
        (p) =>
          p.value != null && (
            <div key={p.dataKey} className="flex justify-between gap-4 text-ink py-0.5">
              <span style={{ color: p.color }}>{p.name}</span>
              <span className="tnum font-semibold">{p.value.toFixed(3)} €/L</span>
            </div>
          )
      )}
    </div>
  );
}

export default function CityAverageChart({
  rows = [],
  marketDelta = null,
  tomorrowDate = null,
  height = 320,
}) {
  const data = rows.map((r) => {
    const hour = r.hour ?? 21;
    const slot = `${r.date} ${String(hour).padStart(2, "0")}`;
    const bc = r.by_city || {};
    const point = { slot, date: r.date, hour };
    const vals = [];
    for (const c of CITIES) {
      const a = bc[c] && typeof bc[c].average === "number" ? bc[c].average : null;
      point[c] = a;
      if (a != null) vals.push(a);
    }
    point.allAvg =
      vals.length > 0
        ? Number((vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(3))
        : null;
    return point;
  });

  let lastIdx = -1;
  for (let i = data.length - 1; i >= 0; i--) {
    if (data[i].allAvg != null) {
      lastIdx = i;
      break;
    }
  }

  const canProject =
    lastIdx >= 0 && marketDelta != null && !isNaN(marketDelta) && tomorrowDate;

  if (canProject) {
    data[lastIdx].projected = data[lastIdx].allAvg;
    const projVal = Number((data[lastIdx].allAvg + marketDelta).toFixed(3));
    data.push({
      slot: `${tomorrowDate} 14`,
      date: tomorrowDate,
      hour: 14,
      projected: projVal,
    });
  }

  const prices = data
    .flatMap((d) => [d.allAvg, d.projected, ...CITIES.map((c) => d[c])])
    .filter((v) => v !== null && v !== undefined);

  if (prices.length === 0) {
    return (
      <div
        className="font-mono text-xs text-secondary py-12 text-center border border-dashed border-line rounded-lg"
        style={{ height }}
        data-testid="city-avg-chart-empty"
      >
        Ei vielä kaupunkikohtaista keskihintadataa. Kertyy klo 14 ja 21
        mittauksista.
      </div>
    );
  }
  const min = Math.min(...prices) - 0.02;
  const max = Math.max(...prices) + 0.02;

  return (
    <div className="w-full" style={{ height }} data-testid="city-avg-chart">
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

          {CITIES.map((c) => (
            <Line
              key={c}
              type="monotone"
              dataKey={c}
              name={c}
              stroke={CITY_COLOR[c]}
              strokeWidth={1.5}
              strokeOpacity={0.55}
              dot={{ r: 2.5, fill: CITY_COLOR[c], stroke: "#fff", strokeWidth: 0.75 }}
              activeDot={{ r: 4 }}
              connectNulls
              isAnimationActive={false}
            />
          ))}

          <Line
            type="monotone"
            dataKey="allAvg"
            name="Kaikkien kaupunkien ka."
            stroke={ALL_COLOR}
            strokeWidth={3}
            dot={{ r: 3.5, fill: ALL_COLOR, stroke: "#fff", strokeWidth: 1.5 }}
            activeDot={{ r: 6 }}
            connectNulls
            isAnimationActive
          />

          {canProject && (
            <Line
              type="monotone"
              dataKey="projected"
              name="Huomisen arvio (markkinaliike)"
              stroke={PROJ_COLOR}
              strokeWidth={2.5}
              strokeDasharray="6 4"
              dot={{ r: 6, fill: PROJ_COLOR, stroke: "#0F172A", strokeWidth: 2 }}
              connectNulls
              isAnimationActive
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
