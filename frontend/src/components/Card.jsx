import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { cn } from "../lib/utils";

export function Card({ children, className = "", testId, dark = false, span = "", ...rest }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={reduce ? undefined : { opacity: 1, y: 0 }}
      transition={reduce ? { duration: 0 } : { duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      data-testid={testId}
      className={cn(
        "relative overflow-hidden station-panel text-ink",
        dark && "station-panel--hero",
        span,
        className
      )}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

export function CardLabel({ children, className = "", ...rest }) {
  return (
    <div
      className={cn(
        "font-mono text-[11px] uppercase tracking-normal text-secondary font-extrabold",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function DeltaBadge({ delta, unit = "EUR/L", suffix = "" }) {
  if (delta === null || delta === undefined || isNaN(delta)) {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-xs px-2.5 py-1 bg-white/5 text-secondary border border-line">
        <Minus size={11} strokeWidth={2.6} />
      </span>
    );
  }

  const n = Number(delta);
  const up = n > 0.0005;
  const down = n < -0.0005;
  const cls = up
    ? "bg-signalUpBg text-signalUp border border-signalUp/20"
    : down
    ? "bg-signalDownBg text-signalDown border border-signalDown/20"
    : "bg-white/5 text-secondary border border-line";
  const Icon = up ? ArrowUp : down ? ArrowDown : Minus;
  const sign = up ? "+" : down ? "-" : "";
  const formatted = Math.abs(n).toFixed(3);

  return (
    <span className={cn("inline-flex items-center gap-1 font-mono text-xs font-semibold px-2.5 py-1", cls)}>
      <Icon size={11} strokeWidth={2.8} />
      {sign}
      {formatted} {unit}
      {suffix}
    </span>
  );
}
