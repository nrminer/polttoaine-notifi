import React from "react";
import { TrendingUp, Calendar, Activity } from "lucide-react";
import { Card, CardLabel } from "./Card";

const PHASE_COLORS = {
  ennen_nousua: "#F59E0B", // amber - before jump
  nousu: "#10B981",        // green - jump happening
  vakaa: "#3B82F6",        // blue - stable
  lasku: "#EC4899",        // pink - decline
};

const PHASE_ICONS = {
  ennen_nousua: TrendingUp,
  nousu: Activity,
  vakaa: Calendar,
  lasku: TrendingUp,
};

export default function CycleIndicator({ result }) {
  const wc = result?.methods?.weekly_cycle;

  if (!wc) {
    return null;
  }

  const cycleStats = wc.cycle_stats || {};
  const currentPhase = wc.current_phase || {};

  // Don't show if cycle not detected
  if (!cycleStats.detected) {
    return null;
  }

  const phase = currentPhase.phase;
  const phaseFi = currentPhase.phase_fi || "Tuntematon";
  const phaseColor = PHASE_COLORS[phase] || "#64748B";
  const PhaseIcon = PHASE_ICONS[phase] || Activity;

  const daysSince = currentPhase.days_since_last_jump;
  const nextJumpDays = currentPhase.next_jump_estimate_days;
  const nextJumpDate = currentPhase.next_jump_date;
  const confidence = currentPhase.confidence || 0;

  return (
    <Card span="" testId="cycle-indicator-card" className="p-6">
      <div className="flex items-center justify-between mb-4">
        <CardLabel>Viikkosykli</CardLabel>
        <Activity size={14} strokeWidth={2.4} className="text-secondary" />
      </div>

      <div className="space-y-4">
        {/* Current Phase */}
        <div className="flex items-center gap-3">
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center"
            style={{ backgroundColor: `${phaseColor}20` }}
          >
            <PhaseIcon size={20} strokeWidth={2.5} style={{ color: phaseColor }} />
          </div>
          <div className="flex-1">
            <div className="font-semibold text-lg" style={{ color: phaseColor }}>
              {phaseFi}
            </div>
            <p className="text-xs text-muted font-mono">
              Luottamus {(confidence * 100).toFixed(0)}%
            </p>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3 pt-3 border-t border-line">
          <div>
            <p className="text-[10px] text-muted uppercase tracking-wider mb-1">
              Viime hypystä
            </p>
            <p className="font-mono text-lg font-bold text-ink">
              {daysSince != null ? `${daysSince} pv` : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-muted uppercase tracking-wider mb-1">
              Seuraava hyppy
            </p>
            <p className="font-mono text-lg font-bold text-ink">
              {nextJumpDays != null ? `~${nextJumpDays} pv` : "—"}
            </p>
          </div>
        </div>

        {nextJumpDate && (
          <div className="bg-brand/5 -mx-6 px-6 py-3 -mb-6 rounded-b-xl">
            <p className="text-xs text-secondary">
              <span className="font-semibold text-brand">Arvioitu seuraava nousu:</span>{" "}
              {new Date(nextJumpDate).toLocaleDateString("fi-FI", {
                weekday: "short",
                day: "numeric",
                month: "numeric",
              })}
            </p>
          </div>
        )}

        {/* Cycle Stats */}
        {cycleStats.avg_cycle_days && (
          <div className="pt-3 border-t border-line">
            <p className="text-[10px] text-muted uppercase tracking-wider mb-2">
              Syklistatistiikka
            </p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div>
                <span className="text-muted">Keskipituus:</span>{" "}
                <span className="font-mono font-semibold text-ink">
                  {cycleStats.avg_cycle_days.toFixed(1)} pv
                </span>
              </div>
              <div>
                <span className="text-muted">Hajonta:</span>{" "}
                <span className="font-mono font-semibold text-ink">
                  ±{cycleStats.std_cycle_days.toFixed(1)} pv
                </span>
              </div>
              <div>
                <span className="text-muted">Hypyt:</span>{" "}
                <span className="font-mono font-semibold text-ink">
                  {cycleStats.n_jumps}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
