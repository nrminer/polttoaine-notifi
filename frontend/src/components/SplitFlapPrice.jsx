import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "../lib/utils";

function formatValue(value, digits) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
}

export default function SplitFlapPrice({
  value,
  digits = 3,
  suffix = "EUR/L",
  testId,
  ariaLabel,
  className = "",
}) {
  const reduce = useReducedMotion();
  const formatted = formatValue(value, digits);
  const chars = formatted.split("");

  return (
    <span
      className={cn("split-flap-price tnum", className)}
      data-testid={testId}
      role="group"
      aria-label={ariaLabel || `${formatted} ${suffix}`}
    >
      <span className="split-flap-price__digits" aria-hidden="true">
        {chars.map((char, index) => (
          <motion.span
            className={cn(
              "split-flap-price__tile",
              char === "." && "split-flap-price__tile--dot"
            )}
            key={`${char}-${index}`}
            initial={reduce ? false : { rotateX: -84, opacity: 0.2 }}
            animate={reduce ? undefined : { rotateX: 0, opacity: 1 }}
            transition={
              reduce
                ? { duration: 0 }
                : { duration: 0.42, delay: index * 0.045, ease: [0.2, 0.86, 0.23, 1] }
            }
          >
            <span>{char}</span>
          </motion.span>
        ))}
      </span>
      <span className="split-flap-price__sr">{formatted}</span>
      {suffix && <span className="split-flap-price__suffix">{suffix}</span>}
    </span>
  );
}
