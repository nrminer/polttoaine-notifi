import React from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
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
  return (
    <div className="bg-white border border-line shadow-lg px-3 py-2 font-mono text-xs">
      <div className="text-secondary mb-1">{fmtDateFi(label)}</div>
      {payload.map((p) => (
        p.value != null && (
          <div key={p.dataKey} className="flex justify-between gap-4 text-ink">
            <span style={{ color: p.color }}>{p.name}</span>
            <span className="tnum">{p.value.toFixed(3)} €/L</span>
          </div>
        )
      ))}
    </div>
  );
}

export default function TrackingChart({ rows = [], tomorrow, height = 320 }) {
  // Yhdistä actual + predicted + tomorrow-piste
  const data = rows.map((r) => ({
    date: r.date,
    actual: r.actual_cheapest,
    predicted: r.predicted_cheapest_for_today,
  }));

  // huomisen ennustepiste yhdistetään lineaarisesti viimeisestä pisteestä
  if (rows.length && tomorrow?.date && tomorrow?.value != null) {
    data.push({
      date: tomorrow.date,
      tomorrow: tomorrow.value,
    });
  }

  const prices = data
    .flatMap((d) => [d.actual, d.predicted, d.tomorrow])
    .filter((v) => v !== null && v !== undefined);
  if (prices.length === 0) {
    return (
      <div
        className="font-mono text-xs text-secondary py-12 text-center border border-dashed border-line"
        style={{ height }}
        data-testid="tracking-chart-empty"
      >
        Ei vielä dataa. Päivittäinen otanta käynnistyy klo 18:00 (Helsinki).
        Aja "Tallenna nyt" pakottaaksesi ensimmäisen pisteen.
      </div>
    );
  }
  const min = Math.min(...prices) - 0.02;
  const max = Math.max(...prices) + 0.02;

  return (
    <div className="w-full" style={{ height }} data-testid="tracking-chart">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, right: 16, left: 8, bottom: 8 }}>
          <CartesianGrid stroke="#E2E8F0" strokeDasharray="2 3" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(d) => {
              if (!d) return "";
              const [, m, day] = d.split("-");
              return `${parseInt(day)}.${parseInt(m)}`;
            }}
            tick={{ fontSize: 11, fill: "#64748B" }}
            tickLine={false}
            axisLine={{ stroke: "#CBD5E1" }}
            minTickGap={20}
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
            wrapperStyle={{ fontSize: "11px", fontFamily: "JetBrains Mono", paddingBottom: 8 }}
          />
          <Line
            type="monotone"
            dataKey="actual"
            name="Toteutunut halvin"
            stroke="#002FA7"
            strokeWidth={3}
            dot={{ r: 4, fill: "#002FA7", stroke: "#fff", strokeWidth: 1 }}
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
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
