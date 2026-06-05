import React from "react";

/**
 * SourceBreakdown component
 *
 * Displays multi-source price data with freshness indicators and agreement level.
 *
 * @param {Object} props
 * @param {Array<{source: string, price: number, age_hours: number, station_count: number}>} props.sources - Array of source data
 * @param {"high"|"medium"|"low"} props.agreementLevel - Agreement level based on price spread
 */
export default function SourceBreakdown({ sources, agreementLevel }) {
  if (!sources || sources.length === 0) return null;

  // Calculate spread
  const prices = sources.map(s => s.price).filter(p => p != null);
  const spread = prices.length >= 2
    ? ((Math.max(...prices) - Math.min(...prices)) * 100).toFixed(1)
    : "0.0";

  // Agreement level mapping
  const agreementConfig = {
    high: { label: "korkea luotettavuus", color: "text-emerald-600" },
    medium: { label: "kohtalainen luotettavuus", color: "text-amber-600" },
    low: { label: "matala luotettavuus", color: "text-red-600" }
  };

  const agreement = agreementConfig[agreementLevel] || agreementConfig.medium;

  // Freshness indicator
  const getFreshnessIcon = (ageHours) => {
    if (ageHours == null) return "⚪";
    if (ageHours < 3) return "🟢";
    if (ageHours <= 8) return "🟡";
    return "🔴";
  };

  // Sort sources by freshness (newest first)
  const sortedSources = [...sources].sort((a, b) => {
    if (a.age_hours == null) return 1;
    if (b.age_hours == null) return -1;
    return a.age_hours - b.age_hours;
  });

  return (
    <div className="mt-3 pt-3 border-t border-line" data-testid="source-breakdown">
      <div className="text-[10px] font-semibold text-secondary uppercase tracking-wider mb-2">
        Lähteet:
      </div>

      <div className="space-y-1.5">
        {sortedSources.map((src, idx) => (
          <div
            key={`${src.source}-${idx}`}
            className="flex items-baseline gap-1.5 text-[11px]"
            data-testid={`source-${src.source}`}
          >
            <span className="inline-block w-3 text-center leading-none" aria-hidden="true">
              {getFreshnessIcon(src.age_hours)}
            </span>
            <span className="font-semibold text-ink min-w-[90px]">
              {src.source}:
            </span>
            <span className="font-mono tnum font-bold text-ink">
              {src.price != null ? `${src.price.toFixed(3)} €` : "—"}
            </span>
            <span className="font-mono text-[10px] text-muted">
              ({src.age_hours != null ? `${Math.round(src.age_hours)}h sitten` : "—"}
              {src.station_count != null ? `, ${src.station_count} asemaa` : ""})
            </span>
          </div>
        ))}
      </div>

      <div className="mt-2.5 pt-2 border-t border-line/50 flex items-center gap-2 text-[10px]">
        <span className="font-mono font-semibold text-secondary">
          Hajonta:
        </span>
        <span className="font-mono tnum font-bold text-ink">
          ±{spread}¢
        </span>
        <span className={`font-semibold ${agreement.color}`}>
          ({agreement.label})
        </span>
      </div>
    </div>
  );
}
