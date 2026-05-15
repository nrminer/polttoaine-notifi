import React from "react";
import { Fuel, Droplet } from "lucide-react";
import { cn } from "../lib/utils";

const FUELS = [
  { id: "95E10", label: "95E10", Icon: Fuel },
  { id: "diesel", label: "Diesel", Icon: Droplet },
];

export default function FuelToggle({ value, onChange, testIdPrefix = "fuel" }) {
  return (
    <div
      className="inline-flex bg-slate-100 p-1 border border-line"
      role="tablist"
      aria-label="Polttoaine"
      data-testid={`${testIdPrefix}-toggle`}
    >
      {FUELS.map(({ id, label, Icon }) => {
        const active = value === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(id)}
            data-testid={`${testIdPrefix}-toggle-${id.toLowerCase()}`}
            className={cn(
              "px-4 h-9 inline-flex items-center gap-2 font-mono text-sm font-semibold transition-colors",
              active
                ? "bg-nordDark text-white"
                : "text-secondary hover:text-ink"
            )}
          >
            <Icon size={14} strokeWidth={2.4} />
            {label}
          </button>
        );
      })}
    </div>
  );
}
