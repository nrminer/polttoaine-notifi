import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { TrendingUp, TrendingDown, Clock, Activity } from "lucide-react";
import { cn } from "../lib/utils";
import { Card, CardLabel, StatNumber, DeltaBadge } from "./Card";

export function RecommendationCard({
  tomorrowPrice,
  todayPrice,
  confidence,
  bestWindow,
  lastUpdated,
  fuel = "95E10",
  className = ""
}) {
  const reduce = useReducedMotion();

  // Calculate delta
  const delta = tomorrowPrice && todayPrice ? tomorrowPrice - todayPrice : null;
  const shouldWait = delta && delta < -0.005; // Wait if dropping by >0.5 cents
  const shouldFillNow = delta && delta > 0.005; // Fill now if rising by >0.5 cents

  // Calculate savings for 50L tank
  const savings = delta ? Math.abs(delta * 50) : null;

  // Confidence-like score mapping. This should not be presented as certainty.
  const getConfidenceLabel = (conf) => {
    if (!conf) return "Ei kalibroitu";
    if (conf >= 0.8) return "Vahva datatuki";
    if (conf >= 0.6) return "Kohtalainen datatuki";
    if (conf >= 0.4) return "Ohut datatuki";
    return "Heikko datatuki";
  };

  const getConfidenceColor = (conf) => {
    if (!conf) return "text-secondary";
    if (conf >= 0.8) return "text-green-600 dark:text-green-400";
    if (conf >= 0.6) return "text-blue-600 dark:text-blue-400";
    if (conf >= 0.4) return "text-amber-600 dark:text-amber-400";
    return "text-red-600 dark:text-red-400";
  };

  // Format last updated time
  const formatLastUpdated = (timestamp) => {
    if (!timestamp) return "—";
    const date = new Date(timestamp);
    const now = new Date();
    const diffMinutes = Math.floor((now - date) / 60000);

    if (diffMinutes < 1) return "juuri nyt";
    if (diffMinutes < 60) return `${diffMinutes} min sitten`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours} h sitten`;
    return date.toLocaleDateString("fi-FI");
  };

  return (
    <Card
      dark
      className={cn("p-6 md:p-8 lg:p-10", className)}
      testId="recommendation-card"
    >
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardLabel className="text-slate-400 mb-1">Huomisen ennuste</CardLabel>
            <h2 className="text-xl md:text-2xl font-semibold text-white">
              {fuel} - Suomi
            </h2>
          </div>

          {/* Data freshness */}
          <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
            <Clock size={12} />
            <span data-testid="recommendation-freshness">
              {formatLastUpdated(lastUpdated)}
            </span>
          </div>
        </div>

        {/* Tomorrow's price - Large hero number */}
        <div className="space-y-2">
          <StatNumber
            value={tomorrowPrice}
            suffix=" €/L"
            digits={3}
            testId="recommendation-tomorrow-price"
            className="text-white"
          />

          {/* Delta badge */}
          {delta !== null && (
            <div className="flex items-center gap-3 flex-wrap">
              <DeltaBadge delta={delta} unit="€/L" />
              {savings !== null && (
                <span className="text-sm text-slate-300 font-mono">
                  ({savings >= 0 ? "+" : "−"}{Math.abs(savings).toFixed(2)} € / 50L)
                </span>
              )}
            </div>
          )}
        </div>

        {/* Recommendation action */}
        <motion.div
          initial={reduce ? false : { scale: 0.96, opacity: 0 }}
          animate={reduce ? undefined : { scale: 1, opacity: 1 }}
          transition={reduce ? { duration: 0 } : { duration: 0.4, delay: 0.1 }}
          className={cn(
            "rounded-lg p-5 border-2",
            shouldWait
              ? "bg-blue-500/10 border-blue-500/40"
              : shouldFillNow
              ? "bg-amber-500/10 border-amber-500/40"
              : "bg-slate-700/30 border-slate-600/40"
          )}
          data-testid="recommendation-action"
        >
          <div className="flex items-start gap-4">
            {/* Icon */}
            <div
              className={cn(
                "flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center",
                shouldWait
                  ? "bg-blue-500/20 text-blue-400"
                  : shouldFillNow
                  ? "bg-amber-500/20 text-amber-400"
                  : "bg-slate-600/30 text-slate-400"
              )}
            >
              {shouldWait ? (
                <TrendingDown size={24} strokeWidth={2.5} />
              ) : shouldFillNow ? (
                <TrendingUp size={24} strokeWidth={2.5} />
              ) : (
                <Activity size={24} strokeWidth={2.5} />
              )}
            </div>

            {/* Action text */}
            <div className="flex-1 min-w-0">
              <h3
                className={cn(
                  "text-xl md:text-2xl font-bold mb-2",
                  shouldWait
                    ? "text-blue-300"
                    : shouldFillNow
                    ? "text-amber-300"
                    : "text-slate-200"
                )}
                data-testid="recommendation-title"
              >
                {shouldWait
                  ? "HUOMENNA VOI OLLA EDULLISEMPI"
                  : shouldFillNow
                  ? "NOUSUPAINETTA"
                  : "EI SELVÄÄ SUUNTAA"}
              </h3>

              <p className="text-sm md:text-base text-slate-300 leading-relaxed">
                {shouldWait
                  ? `Arvio on ${Math.abs(delta).toFixed(3)} €/L tätä päivää alempana. 50 litran vaikutus olisi noin ${savings.toFixed(2)} €.`
                  : shouldFillNow
                  ? `Arvio on ${delta.toFixed(3)} €/L tätä päivää korkeampi. 50 litran vaikutus olisi noin ${savings.toFixed(2)} €.`
                  : "Arvio ei erotu selvästi tämän päivän hinnasta."}
              </p>

              {bestWindow && (
                <p className="text-xs text-slate-400 mt-2 font-mono">
                  Paras aika: {bestWindow}
                </p>
              )}
            </div>
          </div>
        </motion.div>

        {/* Data-support indicator */}
        {confidence !== null && confidence !== undefined && (
          <div className="flex items-center justify-between pt-4 border-t border-slate-700/50">
            <div className="flex items-center gap-3">
              <Activity size={16} className="text-slate-400" />
              <div>
                <CardLabel className="text-slate-500 mb-0.5">Datatuki</CardLabel>
                <span
                  className={cn(
                    "text-sm font-semibold",
                    getConfidenceColor(confidence)
                  )}
                  data-testid="recommendation-confidence"
                >
                  {getConfidenceLabel(confidence)}
                </span>
              </div>
            </div>

            {/* Confidence bar */}
            <div className="flex items-center gap-2">
              <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                <motion.div
                  initial={reduce ? false : { width: 0 }}
                  animate={reduce ? undefined : { width: `${confidence * 100}%` }}
                  transition={reduce ? { duration: 0 } : { duration: 0.6, delay: 0.2 }}
                  className={cn(
                    "h-full rounded-full",
                    confidence >= 0.8
                      ? "bg-green-500"
                      : confidence >= 0.6
                      ? "bg-blue-500"
                      : confidence >= 0.4
                      ? "bg-amber-500"
                      : "bg-red-500"
                  )}
                />
              </div>
              <span className="text-xs font-mono text-slate-400">
                {Math.round(confidence * 100)}%
              </span>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
