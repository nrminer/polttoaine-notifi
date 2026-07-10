import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

import CityOverview from "./CityOverview";


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

test("labels persistence as a comparison level", () => {
  act(() => {
    root.render(
      <CityOverview
        city="Turku"
        fuel="95E10"
        price={1.74}
        average={1.79}
        station="Tuore asema"
        prediction={{
          model_version: "persistence-v1",
          target_date: "2026-07-11",
          ensemble: { value: 1.74 },
        }}
        accuracy={{ summary: { ensemble: { mae: 0.01 } } }}
      />
    );
  });

  expect(container.textContent).toContain("Huomisen vertailutaso");
  expect(container.textContent).toContain("Vertailutaso");
  expect(container.querySelector('[data-testid="tomorrow-cheapest-price-hero"]').textContent).toContain("1.740");
});

test("renders an unavailable forecast without copying the current price", () => {
  act(() => {
    root.render(<CityOverview city="Turku" fuel="diesel" price={1.68} prediction={null} />);
  });

  expect(container.querySelector('[data-testid="today-cheapest-price"]').textContent).toContain("1.680");
  expect(container.querySelector('[data-testid="tomorrow-cheapest-price-hero"]').textContent).toContain("-");
  expect(container.textContent).toContain("Nykyhintaa ei käytetä ennusteen korvikkeena");
});
