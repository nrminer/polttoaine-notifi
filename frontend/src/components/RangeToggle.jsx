import React from "react";
import { cn } from "../lib/utils";

export default function RangeToggle({ value, onChange, options, testIdPrefix = "range" }) {
  return (
    <div
      className="inline-flex bg-slate-100 p-1 border border-line"
      data-testid={`${testIdPrefix}-toggle`}
    >
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            data-testid={`${testIdPrefix}-toggle-${opt.value}`}
            className={cn(
              "px-3 h-8 font-mono text-xs font-semibold transition-colors",
              active ? "bg-nordDark text-white" : "text-secondary hover:text-ink"
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
