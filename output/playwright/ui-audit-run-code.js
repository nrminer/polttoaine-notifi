async (page) => {
  const apiCalls = [];
  const apiErrors = [];
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(err.message));
  page.on("request", (request) => {
    if (request.url().includes("/api/")) {
      apiCalls.push({ method: request.method(), url: request.url() });
    }
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({
      method: request.method(),
      url: request.url(),
      failure: request.failure()?.errorText,
    });
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 400) {
      apiErrors.push({ status: response.status(), url: response.url() });
    }
  });

  const waitFor = async (selector, timeout = 90000) => {
    await page.locator(selector).first().waitFor({ state: "visible", timeout });
  };
  const waitForIdle = async () => {
    await page.waitForFunction(() => {
      const btn = document.querySelector('[data-testid="refresh-prices-btn"]');
      return btn && !btn.disabled;
    }, null, { timeout: 120000 });
  };

  await page.setViewportSize({ width: 1440, height: 1200 });
  await page.goto("http://127.0.0.1:3001/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await waitFor('[data-testid="landing-hero"]', 20000);
  await waitFor('[data-testid="landing-data-plane"]', 20000);
  await page.locator('a[href="#dashboard"]').click();

  const required = [
    '[data-testid="fuel-toggle"]',
    '[data-testid="today-cheapest-price"]',
    '[data-testid="tomorrow-prediction-card"]',
    '[data-testid="tracking-chart-card"]',
    '[data-testid="regional-grid-card"]',
    '[data-testid="factors-card"]',
    '[data-testid="news-card"]',
    '[data-testid="accuracy-card"]',
  ];
  for (const selector of required) await waitFor(selector);
  await waitForIdle();
  await page.waitForTimeout(3000);

  const initialThemeDark = await page.locator("html").evaluate((el) => el.classList.contains("dark"));
  const today95 = await page.locator('[data-testid="today-cheapest-price"]').innerText();
  const tomorrow95 = await page.locator('[data-testid="tomorrow-cheapest-price-hero"]').innerText().catch(() => null);
  const regional95 = await page.locator('[data-testid="regional-grid-card"]').innerText();
  await page.screenshot({
    path: "C:/Users/adama/Downloads/poltto/polttoaine-notifi/output/playwright/cli-dashboard-desktop.png",
    fullPage: true,
  });

  await page.locator('[data-testid="theme-toggle-btn"]').click();
  await page.waitForTimeout(500);
  const toggledThemeDark = await page.locator("html").evaluate((el) => el.classList.contains("dark"));

  const dieselCurrentResponse = page.waitForResponse(
    (response) => response.url().includes("/api/prices/current?fuel=diesel") && response.status() < 400,
    { timeout: 120000 }
  ).then(() => true).catch(() => false);
  const dieselRegionalResponse = page.waitForResponse(
    (response) => response.url().includes("/api/regional?fuel=diesel") && response.status() < 400,
    { timeout: 120000 }
  ).then(() => true).catch(() => false);
  await page.locator('[data-testid="fuel-toggle-diesel"]').click();
  const dieselCurrentLoaded = await dieselCurrentResponse;
  const dieselRegionalLoaded = await dieselRegionalResponse;
  await waitForIdle();
  await page.waitForTimeout(1000);
  const dieselSelected = await page.locator('[data-testid="fuel-toggle-diesel"]').getAttribute("aria-selected");
  const todayDiesel = await page.locator('[data-testid="today-cheapest-price"]').innerText();
  const regionalDiesel = await page.locator('[data-testid="regional-grid-card"]').innerText();

  for (const testId of ["chart-city-Helsinki", "chart-range-14", "chart-slot-14"]) {
    const control = page.locator(`[data-testid="${testId}"]`);
    if (await control.count()) await control.click();
  }

  const sourceToggle = page.locator('[data-testid^="source-toggle-"]').first();
  const sourceToggleCount = await page.locator('[data-testid^="source-toggle-"]').count();
  if (sourceToggleCount) await sourceToggle.click();

  const accuracyToggle = page.locator('[data-testid="accuracy-toggle-details"]');
  const accuracyToggleCount = await accuracyToggle.count();
  if (accuracyToggleCount) await accuracyToggle.click();

  await page.screenshot({
    path: "C:/Users/adama/Downloads/poltto/polttoaine-notifi/output/playwright/cli-dashboard-interacted.png",
    fullPage: true,
  });

  const regionCells = await page.locator('[data-testid^="region-cell-"]').evaluateAll((nodes) =>
    nodes.map((node) => ({
      testId: node.getAttribute("data-testid"),
      text: node.innerText,
    }))
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("http://127.0.0.1:3001/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await waitFor('[data-testid="landing-hero"]', 20000);
  await page.locator('a[href="#dashboard"]').click();
  await waitFor('[data-testid="regional-grid-card"]');
  await page.screenshot({
    path: "C:/Users/adama/Downloads/poltto/polttoaine-notifi/output/playwright/cli-dashboard-mobile.png",
    fullPage: true,
  });

  return {
    initialThemeDark,
    toggledThemeDark,
    dieselSelected,
    today95,
    tomorrow95,
    todayDiesel,
    dieselCurrentLoaded,
    dieselRegionalLoaded,
    sourceToggleCount,
    accuracyToggleCount,
    regionCells,
    regional95,
    regionalDiesel,
    apiErrors,
    failedRequests,
    pageErrors,
    consoleErrors,
    seedPostCalls: apiCalls.filter((call) => call.url.includes("/api/seed")),
    apiCallSummary: apiCalls.map((call) => `${call.method} ${call.url}`),
  };
}
