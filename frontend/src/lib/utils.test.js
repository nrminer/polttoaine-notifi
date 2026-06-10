import { fmtDelta, fmtPct, fmtPrice, fuelLabel } from "./utils";
import { formatModelName } from "./modelName";

test("formats prices and deltas for dashboard display", () => {
  expect(fmtPrice(1.9)).toBe("1.900");
  expect(fmtDelta(0.0123)).toBe("+0.012");
  expect(fmtDelta(-0.0123)).toBe("-0.012");
  expect(fmtPct(1.234)).toBe("+1.23 %");
  expect(fmtPrice(null)).toBe("\u2014");
});

test("formats fuel and model labels", () => {
  expect(fuelLabel("95E10")).toBe("95E10");
  expect(fuelLabel("diesel")).toBe("Diesel");
  expect(formatModelName("claude-fable-5")).toBe("Claude Fable 5");
  expect(formatModelName("claude-opus-4-8")).toBe("Claude Opus 4.8");
  expect(formatModelName("claude-sonnet-4-5-20250929")).toBe("Claude Sonnet 4.5");
  expect(formatModelName(null)).toBeNull();
});
