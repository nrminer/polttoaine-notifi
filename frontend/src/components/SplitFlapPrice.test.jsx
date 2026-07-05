import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import SplitFlapPrice from "./SplitFlapPrice";

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

test("renders price as accessible split-flap characters", () => {
  act(() => {
    root.render(
      <SplitFlapPrice
        value={1.857}
        suffix="EUR/L"
        testId="tomorrow-flap-price"
        ariaLabel="Huomisen ennuste 1.857 euroa litralta"
      />
    );
  });

  const readout = container.querySelector('[data-testid="tomorrow-flap-price"]');
  expect(readout).not.toBeNull();
  expect(readout.getAttribute("aria-label")).toBe("Huomisen ennuste 1.857 euroa litralta");
  expect(readout.querySelectorAll(".split-flap-price__tile")).toHaveLength(5);
  expect(readout.textContent).toContain("1.857");
  expect(readout.textContent).toContain("EUR/L");
});

test("renders an em dash tile when price is missing", () => {
  act(() => {
    root.render(<SplitFlapPrice value={null} testId="empty-flap-price" />);
  });

  const readout = container.querySelector('[data-testid="empty-flap-price"]');
  expect(readout).not.toBeNull();
  expect(readout.textContent).toContain("-");
  expect(readout.querySelectorAll(".split-flap-price__tile")).toHaveLength(1);
});
