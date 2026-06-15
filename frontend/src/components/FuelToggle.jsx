import React from "react";
import { Droplet, Fuel } from "lucide-react";
import { cn } from "../lib/utils";

const FUELS = [
  { id: "95E10", label: "95E10", Icon: Fuel },
  { id: "diesel", label: "Diesel", Icon: Droplet },
];

export default function FuelToggle({ value, onChange, testIdPrefix = "fuel" }) {
  return (
    <div
      className="fuel-switch"
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
            className={cn("fuel-switch__button", active && "fuel-switch__button--active")}
          >
            <Icon size={14} strokeWidth={2.4} />
            {label}
          </button>
        );
      })}
    </div>
  );
}
