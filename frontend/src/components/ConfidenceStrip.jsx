import React from "react";
import { Clock, Database, Store, TrendingUp } from "lucide-react";
import { cn } from "../lib/utils";

/**
 * ConfidenceStrip — horizontal metadata strip showing freshness and measured error
 * Props:
 *  - mostRecentScrape: ISO timestamp of last scrape
 *  - sourcesCount: number of data sources used
 *  - stationsCount: number of stations in the sample
 *  - predictionMAE: historical prediction error in €/L (null if unavailable)
 */
export function ConfidenceStrip({
  mostRecentScrape,
  sourcesCount,
  stationsCount,
  predictionMAE,
  className = "",
}) {
  // Calculate time since scrape
  const timeSince = mostRecentScrape
    ? formatTimeSince(new Date(mostRecentScrape))
    : "—";

  // Format MAE as cents
  const maeText =
    predictionMAE !== null && predictionMAE !== undefined && !isNaN(predictionMAE)
      ? `±${(predictionMAE * 100).toFixed(1)} snt`
      : "—";

  return (
    <div
      data-testid="confidence-strip"
      className={cn(
        "flex flex-wrap items-center gap-x-5 gap-y-2 text-sm",
        className
      )}
    >
      {/* Päivitetty */}
      <div
        className="flex items-center gap-1.5 group relative"
        data-testid="confidence-strip-updated"
      >
        <Clock size={14} className="text-secondary" strokeWidth={2.2} />
        <span className="font-medium text-ink">Päivitetty {timeSince} sitten</span>
        <Tooltip text="Aika viimeisimmästä hintahausta" />
      </div>

      {/* Lähteet */}
      <div
        className="flex items-center gap-1.5 group relative"
        data-testid="confidence-strip-sources"
      >
        <Database size={14} className="text-secondary" strokeWidth={2.2} />
        <span className="font-medium text-ink">
          {sourcesCount ?? "—"} lähdettä
        </span>
        <Tooltip text="Aktiivisten datanlähteiden määrä (polttoaine.net, tankille.fi)" />
      </div>

      {/* Asemat */}
      <div
        className="flex items-center gap-1.5 group relative"
        data-testid="confidence-strip-stations"
      >
        <Store size={14} className="text-secondary" strokeWidth={2.2} />
        <span className="font-medium text-ink">
          {stationsCount ?? "—"} asemaa
        </span>
        <Tooltip text="Otoksessa mukana olevien asemien määrä" />
      </div>

      {/* MAE (keskimääräinen toteutunut poikkeama) */}
      <div
        className="flex items-center gap-1.5 group relative"
        data-testid="confidence-strip-mae"
      >
        <TrendingUp size={14} className="text-secondary" strokeWidth={2.2} />
        <span className="font-medium text-ink">{maeText}</span>
        <Tooltip text="Ennusteen keskimääräinen poikkeama toteutuneista mittauksista" />
      </div>
    </div>
  );
}

function Tooltip({ text }) {
  return (
    <span
      className="invisible group-hover:visible absolute left-0 top-full mt-1 z-50
                 w-max max-w-[240px] px-2.5 py-1.5 text-xs font-normal
                 bg-slate-900 text-white rounded-md shadow-lg pointer-events-none"
      role="tooltip"
    >
      {text}
    </span>
  );
}

function formatTimeSince(date) {
  const now = new Date();
  const diff = Math.floor((now - date) / 1000); // seconds

  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}min`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}pv`;
}
