import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceDot,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";
import { fmtDateFi } from "../lib/utils";

function TooltipBody({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-white border border-line shadow-lg px-3 py-2 font-mono text-xs">
      <div className="text-secondary mb-1">{fmtDateFi(label)}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex justify-between gap-4 text-ink">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="tnum">{p.value?.toFixed(3)} €/L</span>
        </div>
      ))}
    </div>
  );
}

export default function HistoryChart({ data, prediction, height = 280 }) {
  // data: [{ date, price, source }]
  const chartData = (data || []).map((d) => ({
    date: d.date,
    actual: d.price,
  }));
  if (prediction && prediction.target_date && prediction.ensemble != null) {
    chartData.push({
      date: prediction.target_date,
      predicted: prediction.ensemble,
    });
  }
  const prices = chartData
    .map((d) => d.actual ?? d.predicted)
    .filter((v) => v !== undefined && v !== null);
  const min = Math.min(...prices) - 0.02;
  const max = Math.max(...prices) + 0.02;

  return (
    <div className="w-full" style={{ height }} data-testid="history-chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 16, right: 16, left: 8, bottom: 8 }}>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#002FA7" stopOpacity={0.18} />
              <stop offset="100%" stopColor="#002FA7" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#E2E8F0" strokeDasharray="2 3" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(d) => {
              const [y, m, day] = d.split("-");
              return `${parseInt(day)}.${parseInt(m)}`;
            }}
            tick={{ fontSize: 11, fill: "#64748B" }}
            tickLine={false}
            axisLine={{ stroke: "#CBD5E1" }}
            minTickGap={40}
          />
          <YAxis
            domain={[min, max]}
            tickFormatter={(v) => v.toFixed(2)}
            tick={{ fontSize: 11, fill: "#64748B" }}
            tickLine={false}
            axisLine={{ stroke: "#CBD5E1" }}
            width={48}
          />
          <Tooltip content={<TooltipBody />} />
          <Area
            type="monotone"
            dataKey="actual"
            name="Toteutunut"
            stroke="#002FA7"
            strokeWidth={2}
            fill="url(#priceFill)"
            isAnimationActive
            dot={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="predicted"
            name="Ennuste"
            stroke="#FDE047"
            strokeWidth={3}
            dot={{ r: 5, fill: "#FDE047", stroke: "#0F172A", strokeWidth: 2 }}
            isAnimationActive
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
