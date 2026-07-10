import React, { useState } from "react";
import { Calculator, Fuel } from "lucide-react";

import { fmtPrice } from "../lib/utils";


export function litersForBudget(amount, price) {
  const budget = Number(amount);
  const unitPrice = Number(price);
  if (!Number.isFinite(budget) || budget <= 0 || !Number.isFinite(unitPrice) || unitPrice <= 0) {
    return null;
  }
  return budget / unitPrice;
}

export default function FuelPumpCalculator({ price, fuel, city }) {
  const [amount, setAmount] = useState(40);
  const liters = litersForBudget(amount, price);
  const fuelName = fuel === "95E10" ? "95 E10" : "diesel";

  return (
    <section className="compact-calculator" aria-labelledby="calculator-title" data-testid="fuel-pump-card">
      <div>
        <span className="section-kicker">Tankkauslaskuri</span>
        <h2 id="calculator-title">Paljonko budjetilla saa?</h2>
        <p>{city} · {fuelName} · {price != null ? `${fmtPrice(price)} €/l` : "hinta puuttuu"}</p>
      </div>
      <label className="calculator-input">
        <span>Budjetti</span>
        <input
          data-testid="fuel-pump-amount-input"
          type="number"
          min="1"
          step="1"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          onInput={(event) => setAmount(event.target.value)}
          aria-label="Tankkausbudjetti euroina"
        />
        <strong>€</strong>
      </label>
      <div className="calculator-result">
        <Fuel size={20} />
        <span>Saat</span>
        <strong className="tnum" data-testid="fuel-pump-liters">{liters != null ? `${liters.toFixed(2)} l` : "-"}</strong>
      </div>
      <Calculator size={22} className="compact-calculator__icon" aria-hidden="true" />
    </section>
  );
}
