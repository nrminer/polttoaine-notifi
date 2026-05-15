import React from "react";
import { motion } from "framer-motion";
import { cn } from "../lib/utils";

export function Card({ children, className = "", testId, dark = false, span = "", ...rest }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      data-testid={testId}
      className={cn(
        "relative overflow-hidden rounded-none border hover-lift",
        dark
          ? "bg-nordDark text-white border-slate-700"
          : "bg-white text-ink border-line",
        span,
        className
      )}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

export function CardLabel({ children, className = "" }) {
  return (
    <div
      className={cn(
        "font-mono text-[11px] uppercase tracking-[0.2em] text-secondary",
        className
      )}
    >
      {children}
    </div>
  );
}

export function StatNumber({ value, suffix = " €/L", digits = 3, testId, className = "" }) {
  const formatted =
    value === null || value === undefined || isNaN(value)
      ? "—"
      : Number(value).toFixed(digits);
  return (
    <div
      data-testid={testId}
      className={cn("hero-num tnum text-[44px] md:text-[52px] leading-none", className)}
    >
      {formatted}
      <span className="text-[18px] text-secondary font-mono font-medium ml-2 align-baseline">
        {suffix}
      </span>
    </div>
  );
}

export function DeltaBadge({ delta, unit = "€/L", suffix = "" }) {
  if (delta === null || delta === undefined || isNaN(delta)) {
    return (
      <span className="inline-flex items-center font-mono text-xs px-2 py-1 bg-slate-100 text-secondary">
        —
      </span>
    );
  }
  const n = Number(delta);
  const up = n > 0.0005;
  const down = n < -0.0005;
  const cls = up
    ? "bg-signalUpBg text-signalUp"
    : down
    ? "bg-signalDownBg text-signalDown"
    : "bg-slate-100 text-secondary";
  const sign = up ? "▲ +" : down ? "▼ " : "  ";
  return (
    <span className={cn("inline-flex items-center font-mono text-xs font-semibold px-2 py-1", cls)}>
      {sign}
      {n.toFixed(3)} {unit}
      {suffix}
    </span>
  );
}
