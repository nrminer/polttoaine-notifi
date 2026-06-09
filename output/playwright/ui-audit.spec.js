const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");

const outDir = __dirname;
const appUrl = "http://127.0.0.1:3001/";

test("BensaVahti dashboard loads and core controls work", async ({ page }) => {
  test.setTimeout(180000);

  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const apiErrors = [];
  const apiCalls = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => pageErrors.push(err.message));
  page.on("requestfailed", (request) => {
    failedRequests.push({
      method: request.method(),
      url: request.url(),
      failure: request.failure()?.errorText,
    });
  });
  page.on("request", (request) => {
    if (request.url().includes("/api/")) {
      apiCalls.push({ method: request.method(), url: request.url() });
    }
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 400) {
      apiErrors.push({
        status: response.status(),
        url: response.url(),
      });
    }
  });

  await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("landing-hero")).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId("landing-data-plane")).toBeVisible();

  await page.locator('a[href="#dashboard"]').click();
  await expect(page.locator("#dashboard")).toBeVisible();
  await expect(page.getByTestId("fuel-toggle")).toBeVisible({ timeout: 90000 });
  await expect(page.getByTestId("today-cheapest-price")).toBeVisible({ timeout: 90000 });
  await expect(page.getByTestId("tomorrow-prediction-card")).toBeVisible({ timeout: 90000 });
  await expect(page.getByTestId("tracking-chart-card")).toBeVisible({ timeout: 90000 });
  await expect(page.getByTestId("regional-grid-card")).toBeVisible({ timeout: 90000 });
  await expect(page.getByTestId("factors-card")).toBeVisible({ timeout: 90000 });
  await expect(page.getByTestId("news-card")).toBeVisible({ timeout: 90000 });
  await expect(page.getByTestId("accuracy-card")).toBeVisible({ timeout: 90000 });

  await page.screenshot({
    path: path.join(outDir, "dashboard-desktop.png"),
    fullPage: true,
  });

  const wasDark = await page.locator("html").evaluate((el) => el.classList.contains("dark"));
  await page.getByTestId("theme-toggle-btn").click();
  await expect
    .poll(() => page.locator("html").evaluate((el) => el.classList.contains("dark")))
    .toBe(!wasDark);

  await page.getByTestId("fuel-toggle-diesel").click();
  await expect(page.getByTestId("fuel-toggle-diesel")).toHaveAttribute("aria-selected", "true");
  await page.waitForTimeout(6000);

  for (const testId of ["chart-city-Helsinki", "chart-range-14", "chart-slot-14"]) {
    const control = page.getByTestId(testId);
    if (await control.count()) {
      await control.click();
    }
  }

  const sourceToggle = page.locator('[data-testid^="source-toggle-"]').first();
  if (await sourceToggle.count()) {
    await sourceToggle.click();
  }

  const accuracyToggle = page.getByTestId("accuracy-toggle-details");
  if (await accuracyToggle.count()) {
    await accuracyToggle.click();
  }

  await page.screenshot({
    path: path.join(outDir, "dashboard-interacted.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("landing-hero")).toBeVisible({ timeout: 20000 });
  await page.locator('a[href="#dashboard"]').click();
  await expect(page.getByTestId("regional-grid-card")).toBeVisible({ timeout: 90000 });
  await page.screenshot({
    path: path.join(outDir, "dashboard-mobile.png"),
    fullPage: true,
  });

  const report = {
    consoleErrors,
    pageErrors,
    failedRequests,
    apiErrors,
    apiCalls,
    desktopRegionalText: await page.getByTestId("regional-grid-card").innerText(),
    seedPostCalls: apiCalls.filter((call) => call.url.includes("/api/seed")),
  };
  fs.writeFileSync(path.join(outDir, "ui-audit-result.json"), JSON.stringify(report, null, 2));

  expect(pageErrors).toEqual([]);
  expect(apiErrors).toEqual([]);
  expect(report.seedPostCalls).toEqual([]);
});
