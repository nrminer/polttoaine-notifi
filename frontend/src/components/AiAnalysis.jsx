import React from "react";
import { Brain, Sparkles } from "lucide-react";
import { Card, CardLabel } from "./Card";

export default function AiAnalysis({ ai, brent, eurUsd }) {
  const explanation = ai?.explanation || "Aja ennustus saadaksesi AI-analyysi.";
  const direction = ai?.direction;
  const value = ai?.value;

  return (
    <Card
      dark
      testId="ai-analysis-card"
      className="p-6 md:p-7 relative"
    >
      <div className="absolute inset-0 opacity-[0.12] mix-blend-overlay pointer-events-none"
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
          <CardLabel className="text-accent">AI-analyysi · Claude Sonnet 4.5</CardLabel>
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
                className="font-mono text-[11px] px-2 py-1 bg-white/10 text-accent border border-accent/30 rounded-none"
              >
                {d}
              </span>
            ))}
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-end gap-x-8 gap-y-3">
          {value != null && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
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
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                Suunta
              </div>
              <div
                data-testid="ai-direction"
                className="font-display text-2xl font-bold"
                style={{
                  color:
                    direction === "up"
                      ? "#FCA5A5"
                      : direction === "down"
                      ? "#86EFAC"
                      : "#E2E8F0",
                }}
              >
                {direction === "up" ? "↑ NOUSU" : direction === "down" ? "↓ LASKU" : "→ TASAINEN"}
              </div>
            </div>
          )}
          {brent != null && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                Brent
              </div>
              <div className="font-mono tnum text-lg">{Number(brent).toFixed(2)} <span className="text-slate-400 text-sm">USD</span></div>
            </div>
          )}
          {eurUsd != null && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                EUR/USD
              </div>
              <div className="font-mono tnum text-lg">{Number(eurUsd).toFixed(4)}</div>
            </div>
          )}
        </div>
        <div className="mt-5 flex items-center gap-2 text-[11px] text-slate-400 font-mono">
          <Sparkles size={12} className="text-accent" />
          AI tarkastelee historiaa, kausivaihtelua, Brent-hintaa ja EUR/USD-kurssia
        </div>
      </div>
    </Card>
  );
}
