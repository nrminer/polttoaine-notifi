import React from "react";
import { MessageSquareText, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Card, CardLabel } from "./Card";
import { formatModelName } from "../lib/modelName";

function DirectionBadge({ direction }) {
  if (!direction) return null;
  if (direction === "up")
    return (
      <span className="inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-red-500/15 border border-red-400/30 text-red-300 font-display text-sm font-bold uppercase tracking-wider">
        <TrendingUp size={13} /> Nousu
      </span>
    );
  if (direction === "down")
    return (
      <span className="inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-emerald-500/15 border border-emerald-400/30 text-emerald-300 font-display text-sm font-bold uppercase tracking-wider">
        <TrendingDown size={13} /> Lasku
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-slate-700/40 border border-slate-600/30 text-slate-300 font-display text-sm font-bold uppercase tracking-wider">
      <Minus size={13} /> Tasainen
    </span>
  );
}

/* Visual confidence interval band: shows lo / value / hi as a positioned
   marker over a horizontal range. Anchor = live price (or value itself
   if no anchor available) so the band reads as a directional gap. */
function CIBand({ lo, hi, value, anchor }) {
  if (lo == null || hi == null || value == null) return null;
  const min = Math.min(lo, anchor ?? value);
  const max = Math.max(hi, anchor ?? value);
  const width = Math.max(0.001, max - min);
  const pct = (x) => ((x - min) / width) * 100;
  const leftLo = Math.max(0, pct(lo));
  const widthLoHi = Math.max(2, pct(hi) - leftLo);
  const valuePos = Math.min(100, Math.max(0, pct(value)));
  const anchorPos =
    anchor != null ? Math.min(100, Math.max(0, pct(anchor))) : null;
  return (
    <div className="mt-2">
      <div className="relative h-3 rounded-full bg-white/5 border border-slate-700/60">
        <div
          className="absolute top-0 bottom-0 rounded-full bg-accent/40"
          style={{ left: `${leftLo}%`, width: `${widthLoHi}%` }}
        />
        {anchorPos != null && (
          <span
            className="absolute -top-0.5 -bottom-0.5 w-px bg-slate-400"
            style={{ left: `${anchorPos}%` }}
            title="live-ankkuri"
          />
        )}
          <span
            className="absolute -top-1 -bottom-1 w-0.5 bg-accent"
            style={{ left: `${valuePos}%` }}
          title="LLM-arvio"
        />
      </div>
      <div className="mt-1.5 flex justify-between font-mono text-[11px] text-slate-500 tnum">
        <span>{lo.toFixed(3)}</span>
        <span
          className="text-slate-400"
          title="Mallin itse raportoima väli; kattavuutta ei ole kalibroitu toteumiin"
        >
          mallin antama väli
        </span>
        <span>{hi.toFixed(3)}</span>
      </div>
    </div>
  );
}

export default function AiAnalysis({ ai, brent, eurUsd, anchor }) {
  const explanation = ai?.explanation || "Aja ennuste saadaksesi LLM-arvion.";
  const direction = ai?.direction;
  const value = ai?.value;
  const lo = ai?.confidence_low;
  const hi = ai?.confidence_high;
  const modelLabel = formatModelName(ai?.model);
  const drivers = (ai?.key_drivers || []).slice(0, 4);

  return (
    <Card dark testId="ai-analysis-card" className="p-6 md:p-7 relative">
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none rounded-xl"
        style={{
          background:
            "linear-gradient(180deg, rgba(15, 23, 42, 0.24), rgba(15, 23, 42, 0))",
        }}
      />
      <div className="relative z-10">
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2">
            <MessageSquareText size={14} className="text-accent" strokeWidth={2.4} />
            <CardLabel className="text-accent" data-testid="ai-model-label">
              LLM-arvio{modelLabel ? ` · ${modelLabel}` : ""}
            </CardLabel>
          </div>
          {direction && (
            <div data-testid="ai-direction">
              <DirectionBadge direction={direction} />
            </div>
          )}
        </div>

        {/* Hero number row */}
        <div className="flex items-end gap-6 flex-wrap" data-testid="ai-value-row">
          {value != null && (
            <div>
              <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-1">
                LLM-arvio
              </div>
              <div className="font-display font-black tnum text-4xl md:text-5xl text-white leading-none">
                {Number(value).toFixed(3)}
                <span className="text-slate-400 font-mono font-medium text-base ml-2">€/L</span>
              </div>
            </div>
          )}
          {anchor != null && value != null && (
            <div>
              <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-1">
                Δ live
              </div>
              <div
                className={`font-mono tnum text-xl font-semibold ${
                  value - anchor > 0.0005
                    ? "text-red-300"
                    : value - anchor < -0.0005
                    ? "text-emerald-300"
                    : "text-slate-300"
                }`}
              >
                {value - anchor > 0 ? "+" : ""}
                {((value - anchor) * 1000).toFixed(1)} m€/L
              </div>
            </div>
          )}
        </div>

        {/* Confidence interval band */}
        <CIBand lo={lo} hi={hi} value={value} anchor={anchor} />

        {/* Explanation — sized like normal body text, not a giant quote */}
        <p
          className="mt-5 text-slate-200 text-sm md:text-base leading-relaxed max-w-prose"
          data-testid="ai-explanation"
        >
          {explanation}
        </p>

        {/* Key drivers — numbered, not just a flat row of chips */}
        {drivers.length > 0 && (
          <div className="mt-5" data-testid="ai-drivers">
            <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-2">
              Avainajurit
            </div>
            <ol className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {drivers.map((d, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2.5 px-3 py-2 rounded-md bg-white/5 border border-slate-700/60"
                >
                  <span className="font-mono text-[11px] tnum text-accent shrink-0 mt-0.5 w-4">
                    {i + 1}
                  </span>
                  <span className="text-slate-200 text-[13px] leading-snug">{d}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* Backdrop macro row */}
        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3 pt-4 border-t border-slate-700/60">
          {brent != null && (
            <div>
              <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-1">
                Brent
              </div>
              <div className="font-mono tnum text-base font-semibold text-slate-100">
                {Number(brent).toFixed(2)}
                <span className="text-slate-500 text-[11px] ml-1">USD/bbl</span>
              </div>
            </div>
          )}
          {eurUsd != null && (
            <div>
              <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-slate-400 mb-1">
                EUR/USD
              </div>
              <div className="font-mono tnum text-base font-semibold text-slate-100">
                {Number(eurUsd).toFixed(4)}
              </div>
            </div>
          )}
          <div className="ml-auto flex items-center gap-1.5 text-[11px] text-slate-500 font-mono">
            markkinariskit käsitellään erikseen Brent-liikkeestä
          </div>
        </div>
      </div>
    </Card>
  );
}
