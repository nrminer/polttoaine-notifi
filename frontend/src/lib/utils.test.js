import { fmtPrice } from "./utils";
import { formatModelName } from "./modelName";

test("formats prices for dashboard display", () => {
  expect(fmtPrice(1.9)).toBe("1.900");
  expect(fmtPrice(null)).toBe("\u2014");
});

test("formats model labels", () => {
  expect(formatModelName("claude-fable-5")).toBe("Claude Fable 5");
  expect(formatModelName("claude-opus-4-8")).toBe("Claude Opus 4.8");
  expect(formatModelName("claude-sonnet-4-5-20250929")).toBe("Claude Sonnet 4.5");
  expect(formatModelName(null)).toBeNull();
});
