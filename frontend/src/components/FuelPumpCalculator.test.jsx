import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

import FuelPumpCalculator, { litersForBudget } from "./FuelPumpCalculator";


global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

test("calculates liters from the selected city price", () => {
  expect(litersForBudget(40, 1.8)).toBeCloseTo(22.222, 3);
  expect(litersForBudget(40, null)).toBeNull();
});

test("renders and updates the compact city calculator", () => {
  act(() => {
    root.render(<FuelPumpCalculator price={1.8} fuel="95E10" city="Turku" />);
  });

  const input = container.querySelector('[data-testid="fuel-pump-amount-input"]');
  expect(container.textContent).toContain("Turku");
  expect(container.textContent).toContain("95 E10");
  expect(container.querySelector('[data-testid="fuel-pump-liters"]').textContent).toContain("22.22");

  act(() => {
    input.value = "50";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  expect(container.querySelector('[data-testid="fuel-pump-liters"]').textContent).toContain("27.78");
});
