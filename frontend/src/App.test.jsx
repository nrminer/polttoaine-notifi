import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import {
  fetchAccuracy,
  fetchCurrent,
  fetchFactors,
  fetchLatestPrediction,
  fetchNews,
  fetchRegional,
  fetchTrackHistory,
} from "./lib/api";


jest.mock("./lib/api", () => ({
  fetchAccuracy: jest.fn(),
  fetchCurrent: jest.fn(),
  fetchFactors: jest.fn(),
  fetchLatestPrediction: jest.fn(),
  fetchNews: jest.fn(),
  fetchRegional: jest.fn(),
  fetchTrackHistory: jest.fn(),
}));
jest.mock("./components/Card", () => ({
  Card: ({ children, testId }) => <section data-testid={testId}>{children}</section>,
  CardLabel: ({ children }) => <span>{children}</span>,
}));
jest.mock("./components/FuelToggle", () => () => null);
jest.mock("./components/FuelPumpCalculator", () => () => null);
jest.mock("./components/TrackingChart", () => () => null);
jest.mock("./components/MethodTable", () => () => null);
jest.mock("./components/AiAnalysis", () => () => null);
jest.mock("./components/RegionalGrid", () => () => null);
jest.mock("./components/AccuracyTracker", () => () => null);
jest.mock("./components/FactorsCard", () => () => null);
jest.mock("./components/NewsCard", () => () => null);


global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("bensavahti-home-city", "Turku");
  fetchCurrent.mockImplementation((fuel) => Promise.resolve({ data: {
    fuel,
    fetched_at: "2026-07-10T18:00:00Z",
    national_min: 1.6,
    cheap_sample_avg: 1.7,
    stations_count: 20,
    by_city: {
      Turku: { min: 1.75, count: 4, station_min: "Turun asema", sources: [] },
    },
  } }));
  fetchRegional.mockResolvedValue({ data: {
    fuel: "95E10",
    fetched_at: "2026-07-10T18:00:00Z",
    rows: [{ region: "Turku", price: 1.74, station: "Tuore asema", fresh: true }],
  } });
  fetchLatestPrediction.mockImplementation((requestedFuel, region) => Promise.resolve({ data: {
    available: true,
    fuel: requestedFuel,
    region,
    target_date: "2026-07-11",
    current_price: region === "Turku" ? 1.74 : 1.6,
    ensemble: { value: region === "Turku" ? 1.76 : 1.61 },
    methods: {},
    data_sources: {},
    prediction_confidence: { prediction_mae: 0.01 },
  } }));
  fetchAccuracy.mockImplementation((requestedFuel, region) => Promise.resolve({ data: {
    fuel: requestedFuel,
    region,
    summary: { ensemble: { n: 3, mae: 0.01 } },
  } }));
  fetchFactors.mockResolvedValue({ data: {} });
  fetchNews.mockResolvedValue({ data: { items: [] } });
  fetchTrackHistory.mockResolvedValue({ data: { rows: [], summary: {} } });

  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  jest.clearAllMocks();
});

test("uses the persisted home city for the primary forecast", async () => {
  await act(async () => {
    root.render(<App />);
  });

  const select = container.querySelector('[data-testid="home-city-select"]');
  expect(select.value).toBe("Turku");
  expect(fetchLatestPrediction).toHaveBeenCalledWith("95E10", "Turku");
  expect(container.querySelector('[data-testid="today-cheapest-price"]').textContent).toContain("1.740");
  expect(container.querySelector('[data-testid="tomorrow-cheapest-price-hero"]').textContent).toContain("1.760");
  expect(container.querySelector('[data-testid="current-min-price"]').textContent).toContain("1.600");
});

test("does not present today's city price as a missing forecast", async () => {
  fetchLatestPrediction.mockImplementation((requestedFuel, region) => Promise.resolve({ data: region === "Turku"
    ? { available: false }
    : {
        available: true,
        fuel: requestedFuel,
        region,
        ensemble: { value: 1.61 },
        methods: {},
      },
  }));

  await act(async () => {
    root.render(<App />);
  });

  expect(container.querySelector('[data-testid="today-cheapest-price"]').textContent).toContain("1.740");
  expect(container.querySelector('[data-testid="tomorrow-cheapest-price-hero"]').textContent).toContain("-");
  expect(container.textContent).toContain("Huomisen arvio puuttuu");
});
