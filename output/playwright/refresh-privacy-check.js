async (page) => {
  const apiErrors = [];
  const pageErrors = [];
  const failedRequests = [];

  page.on('pageerror', (err) => pageErrors.push(err.message));
  page.on('requestfailed', (request) => {
    failedRequests.push({
      method: request.method(),
      url: request.url(),
      failure: request.failure()?.errorText,
    });
  });
  page.on('response', (response) => {
    if (response.url().includes('/api/') && response.status() >= 400) {
      apiErrors.push({ status: response.status(), url: response.url() });
    }
  });

  await page.goto('http://127.0.0.1:3001/#dashboard', { waitUntil: 'domcontentloaded' });
  await page.locator('[data-testid="refresh-prices-btn"]').waitFor({ state: 'visible', timeout: 30000 });
  await page.locator('[data-testid="refresh-prices-btn"]').click();
  await page.waitForFunction(() => {
    const btn = document.querySelector('[data-testid="refresh-prices-btn"]');
    return btn && !btn.disabled;
  }, null, { timeout: 120000 });

  const privacyHref = await page.locator('[data-testid="privacy-link"]').getAttribute('href');
  const privacyResponse = await page.goto(`http://127.0.0.1:3001${privacyHref}`, {
    waitUntil: 'domcontentloaded',
    timeout: 30000,
  });

  return {
    refreshCompleted: true,
    apiErrors,
    failedRequests,
    pageErrors,
    privacyHref,
    privacyStatus: privacyResponse?.status(),
    privacyTitle: await page.title(),
  };
}
