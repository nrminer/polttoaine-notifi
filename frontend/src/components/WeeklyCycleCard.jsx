import React from "react";

const DAYS = ["Ma", "Ti", "Ke", "To", "Pe", "La", "Su"];
const DAY_FULL = {
  Ma: "Maanantai",
  Ti: "Tiistai",
  Ke: "Keskiviikko",
  To: "Torstai",
  Pe: "Perjantai",
  La: "Lauantai",
  Su: "Sunnuntai",
};

const PHASE_CONFIG = {
  Vakaa: {
    color: "#22C55E",
    bg: "#DCFCE7",
    bgDark: "#166534",
    label: "Vakaa",
    description: "Hinnat vakaita",
  },
  Nousu: {
    color: "#F59E0B",
    bg: "#FEF3C7",
    bgDark: "#92400E",
    label: "Nousu",
    description: "Hinnat nousevat",
  },
  Lasku: {
    color: "#3B82F6",
    bg: "#DBEAFE",
    bgDark: "#1E40AF",
    label: "Lasku",
    description: "Hinnat laskevat",
  },
};

export default function WeeklyCycleCard({
  currentPhase = "Vakaa",
  daysUntilJump = null,
  weekPattern = [],
  currentDayIndex = null,
}) {
  const phaseConfig = PHASE_CONFIG[currentPhase] || PHASE_CONFIG.Vakaa;

  // Auto-detect current day if not provided
  const today = currentDayIndex !== null ? currentDayIndex : (() => {
    const d = new Date().getDay();
    return d === 0 ? 6 : d - 1; // Convert Sunday=0 to index 6
  })();

  // Build week data: weekPattern is array of phase names for each day
  const weekData = DAYS.map((day, idx) => ({
    day,
    dayFull: DAY_FULL[day],
    phase: weekPattern[idx] || "Vakaa",
    isCurrent: today === idx,
  }));

  return (
    <div
      className="bg-white dark:bg-surface border border-line rounded-lg p-4"
      data-testid="weekly-cycle-card"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide">
          Viikkosykli
        </h3>
        <div
          className="px-2.5 py-1 rounded-md text-xs font-semibold"
          style={{
            backgroundColor: phaseConfig.bg,
            color: phaseConfig.color,
          }}
          data-testid="cycle-phase-badge"
        >
          {phaseConfig.label}
        </div>
      </div>

      {/* Week visualization */}
      <div className="flex gap-2 mb-4" data-testid="week-visualization">
        {weekData.map((d, idx) => {
          const dayPhase = PHASE_CONFIG[d.phase] || PHASE_CONFIG.Vakaa;
          const isActive = d.isCurrent;
          return (
            <div
              key={idx}
              className="flex-1 flex flex-col items-center gap-1.5"
              data-testid={`week-day-${idx}`}
            >
              <div
                className={`w-full h-12 rounded-md transition-all ${
                  isActive
                    ? "ring-2 ring-offset-2 dark:ring-offset-surface"
                    : "opacity-75"
                }`}
                style={{
                  backgroundColor: dayPhase.bg,
                  borderColor: dayPhase.color,
                  borderWidth: isActive ? "2px" : "1px",
                  ringColor: dayPhase.color,
                }}
                title={`${d.dayFull}: ${dayPhase.description}`}
              />
              <span
                className={`text-xs font-mono ${
                  isActive
                    ? "font-bold text-ink"
                    : "text-secondary"
                }`}
              >
                {d.day}
              </span>
            </div>
          );
        })}
      </div>

      {/* Cycle info */}
      <div className="flex items-center justify-between pt-3 border-t border-line">
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] uppercase tracking-wider text-muted">
            Vaihe
          </span>
          <span className="text-sm font-semibold text-ink" data-testid="cycle-phase-text">
            {phaseConfig.description}
          </span>
        </div>

        {daysUntilJump != null && daysUntilJump >= 0 && (
          <div className="flex flex-col gap-0.5 items-end">
            <span className="text-[10px] uppercase tracking-wider text-muted">
              Seuraavaan muutokseen
            </span>
            <span className="text-sm font-semibold text-ink tnum" data-testid="days-until-jump">
              {daysUntilJump === 0 ? "Tänään" : `${daysUntilJump} pv`}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
