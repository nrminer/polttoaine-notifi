import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

import RegionalGrid from "./RegionalGrid";


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

test("pins the selected city and lets another city become home", () => {
  const onSelect = jest.fn();
  act(() => {
    root.render(
      <RegionalGrid
        fuel="95E10"
        selectedCity="Turku"
        onSelectCity={onSelect}
        data={{
          max_age_hours: 24,
          rows: [
            { region: "Helsinki", price: 1.7, station: "Helsinki A", fresh: true, age_hours: 2 },
            { region: "Turku", price: 1.75, station: "Turku A", fresh: true, age_hours: 1 },
          ],
        }}
        cityData={{ Turku: { mean: 1.8, sources: [] } }}
      />
    );
  });

  const cityButtons = container.querySelectorAll(".city-name-button");
  expect(cityButtons[0].textContent).toContain("Turku");

  act(() => cityButtons[1].dispatchEvent(new MouseEvent("click", { bubbles: true })));
  expect(onSelect).toHaveBeenCalledWith("Helsinki");
});
