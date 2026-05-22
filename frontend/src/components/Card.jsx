import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowUp, ArrowDown, Minus } from "lucide-react";
import { cn } from "../lib/utils";

export function Card({ children, className = "", testId, dark = false, span = "", ...rest }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={reduce ? undefined : { opacity: 1, y: 0 }}
      transition={reduce ? { duration: 0 } : { duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      data-testid={testId}
      className={cn(
        "relative overflow-hidden rounded-xl border hover-lift",
        dark
          ? "bg-nordDark text-white border-slate-700/80"
          : "bg-white text-ink border-line shadow-card",
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
        "font-mono text-[11px] uppercase tracking-[0.18em] text-secondary",
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
      <span className="inline-flex items-center gap-1 font-mono text-xs px-2.5 py-1 rounded-md bg-slate-100 text-secondary">
        <Minus size={11} strokeWidth={2.6} />
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
  const Icon = up ? ArrowUp : down ? ArrowDown : Minus;
  const sign = up ? "+" : down ? "−" : "";
  const formatted = Math.abs(n).toFixed(3);
  return (
    <span className={cn("inline-flex items-center gap-1 font-mono text-xs font-semibold px-2.5 py-1 rounded-md", cls)}>
      <Icon size={11} strokeWidth={2.8} />
      {sign}
      {formatted} {unit}
      {suffix}
    </span>
  );
}
