import React from "react";
import { Brain, Sparkles, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Card, CardLabel } from "./Card";
import { formatModelName } from "../lib/modelName";

function DirectionBadge({ direction }) {
  if (!direction) return null;
  if (direction === "up")
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/15 border border-red-400/30 text-red-300 font-display text-base font-bold">
        <TrendingUp size={14} /> NOUSU
      </span>
    );
  if (direction === "down")
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/15 border border-emerald-400/30 text-emerald-300 font-display text-base font-bold">
        <TrendingDown size={14} /> LASKU
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-700/40 border border-slate-600/30 text-slate-300 font-display text-base font-bold">
      <Minus size={14} /> TASAINEN
    </span>
  );
}

export default function AiAnalysis({ ai, brent, eurUsd }) {
  const explanation = ai?.explanation || "Aja ennustus saadaksesi AI-analyysi.";
  const direction = ai?.direction;
  const value = ai?.value;
  const modelLabel = formatModelName(ai?.model);

  return (
    <Card
      dark
      testId="ai-analysis-card"
      className="p-6 md:p-7 relative"
    >
      <div className="absolute inset-0 opacity-[0.12] mix-blend-overlay pointer-events-none rounded-xl"
        style={{
          backgroundImage:
            "url(https://static.prod-images.emergentagent.com/jobs/fbe4dcec-63a2-4ae5-ab80-570a0bc91b44/images/2f4ce133904abe0795e741e29b1017783b57035191543b365ba039243069fe63.png)",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      />
      <div className="relative z-10">
        <div className="flex items-center gap-2 mb-4">
          <Brain size={14} className="text-accent" strokeWidth={2.4} />
          <CardLabel className="text-accent" data-testid="ai-model-label">
            AI-analyysi{modelLabel ? ` · ${modelLabel}` : ""}
          </CardLabel>
        </div>
        <p
          className="font-display text-2xl md:text-3xl tracking-tighter leading-tight"
          data-testid="ai-explanation"
        >
          {explanation}
        </p>

        {ai?.key_drivers && ai.key_drivers.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2" data-testid="ai-drivers">
            {ai.key_drivers.slice(0, 4).map((d, i) => (
              <span
                key={i}
                className="font-mono text-[11px] px-2.5 py-1 rounded-md bg-white/8 text-accent border border-accent/25"
              >
                {d}
              </span>
            ))}
          </div>
        )}

        <div className="mt-6 flex flex-wrap items-end gap-x-6 gap-y-4">
          {value != null && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1">
                Mallin ennuste
              </div>
              <div className="font-mono tnum text-3xl font-bold">
                {Number(value).toFixed(3)}
                <span className="text-sm text-slate-400 ml-1">€/L</span>
              </div>
            </div>
          )}
          {direction && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1">
                Suunta
              </div>
              <div data-testid="ai-direction">
                <DirectionBadge direction={direction} />
              </div>
            </div>
          )}
          {brent != null && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1">
                Brent
              </div>
              <div className="font-mono tnum text-lg font-semibold">
                {Number(brent).toFixed(2)}
                <span className="text-slate-400 text-sm ml-1">USD</span>
              </div>
            </div>
          )}
          {eurUsd != null && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1">
                EUR/USD
              </div>
              <div className="font-mono tnum text-lg font-semibold">
                {Number(eurUsd).toFixed(4)}
              </div>
            </div>
          )}
        </div>
        <div className="mt-5 flex items-center gap-2 text-[11px] text-slate-400 font-mono">
          <Sparkles size={12} className="text-accent shrink-0" />
          AI tarkastelee historiaa, kausivaihtelua, Brent-hintaa ja EUR/USD-kurssia
        </div>
      </div>
    </Card>
  );
}
