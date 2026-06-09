async (page) => {
  await page.goto('http://127.0.0.1:3001/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => localStorage.removeItem('theme'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.locator('[data-testid="landing-hero"]').waitFor({ state: 'visible', timeout: 20000 });
  return {
    defaultDark: await page.locator('html').evaluate((el) => el.classList.contains('dark')),
    title: await page.title(),
  };
}
