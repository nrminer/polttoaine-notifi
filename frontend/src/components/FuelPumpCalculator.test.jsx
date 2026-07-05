import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import FuelPumpCalculator, { buildPumpRows } from "./FuelPumpCalculator";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

test("derives 98E from 95E and calculates extra liters versus average pump", () => {
  const rows = buildPumpRows({
    amount: 40,
    petrol95: { national_min: 1.8, cheap_sample_avg: 2.0 },
    diesel: { national_min: 1.6, cheap_sample_avg: 1.7 },
  });

  expect(rows.map((row) => row.id)).toEqual(["95e", "98e", "diesel"]);
  expect(rows[0].cheapestPrice).toBeCloseTo(1.8);
  expect(rows[0].liters).toBeCloseTo(22.222, 3);
  expect(rows[0].extraLiters).toBeCloseTo(2.222, 3);
  expect(rows[1].cheapestPrice).toBeCloseTo(1.9);
  expect(rows[1].averagePrice).toBeCloseTo(2.1);
  expect(rows[1].derived).toBe(true);
});

test("renders a 40 euro pump ticket and lets the amount change", () => {
  act(() => {
    root.render(
      <FuelPumpCalculator
        petrol95={{ national_min: 1.8, cheap_sample_avg: 2.0 }}
        diesel={{ national_min: 1.6, cheap_sample_avg: 1.7 }}
      />
    );
  });

  const input = container.querySelector('[data-testid="fuel-pump-amount-input"]');
  expect(input.value).toBe("40");
  expect(container.querySelector('[data-testid="fuel-pump-liters-95e"]').textContent).toContain("22.22");
  expect(container.querySelector('[data-testid="fuel-pump-extra-95e"]').textContent).toContain("+2.22 L enemm\u00e4n kuin keskihinnalla");
  expect(container.textContent).toContain("Mit\u00e4 euroilla saa asemalla");
  expect(container.textContent).toContain("95E + 10 snt/L");
  expect(container.querySelector('[data-testid="fuel-pump-price-98e"]').textContent).toContain("1.900");

  act(() => {
    input.value = "50";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  expect(container.querySelector('[data-testid="fuel-pump-liters-95e"]').textContent).toContain("27.78");
});
