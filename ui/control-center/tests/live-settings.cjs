const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_BIN, headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [],
      external = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('request', (request) => {
      if (!request.url().startsWith(process.env.GUI_TEST_ORIGIN)) external.push(request.url());
    });
    await page.goto(process.env.GUI_TEST_ORIGIN + '/#token=offline-configuration-browser');
    await page.getByRole('link', { name: 'Settings', exact: true }).click();
    await page.getByRole('heading', { name: 'Project settings', exact: true }).waitFor();
    await page.getByRole('link', { name: 'models', exact: true }).click();
    await page.getByLabel('Model', { exact: true }).selectOption('alternate-model');
    await page.getByRole('button', { name: 'Save my selection', exact: true }).click();
    await page.getByText(/Local selection saved/).waitFor();
    await page.getByText(/Effective model: alternate-model/).waitFor();
    const screenshots = path.resolve(process.env.CONFIGURATION_SCREENSHOTS);
    fs.mkdirSync(screenshots, { recursive: true });
    await page.screenshot({ path: path.join(screenshots, 'models-desktop.png'), fullPage: true });
    await page.getByRole('link', { name: 'workflow', exact: true }).click();
    const input = page.locator('input[type=number]').first();
    await input.fill('6');
    await page.getByRole('button', { name: 'Save shared proposal', exact: true }).click();
    await page.getByRole('heading', { name: 'Exact shared proposal' }).waitFor();
    await page.getByRole('button', { name: 'Prepare owner approval handoff' }).click();
    await page.getByText(/Exact approval digest:/).waitFor();
    assert(await page.getByRole('button', { name: 'Copy terminal command' }).isVisible());
    await page.screenshot({ path: path.join(screenshots, 'owner-handoff.png'), fullPage: true });
    await page.getByRole('link', { name: 'directories', exact: true }).click();
    await page.getByRole('heading', { name: 'Current binding', exact: true }).waitFor();
    assert((await page.locator('cc-settings-page').textContent()).includes('publication'));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('link', { name: 'overview', exact: true }).click();
    await page.screenshot({ path: path.join(screenshots, 'overview-mobile.png'), fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
    await page.getByRole('button', { name: 'Dark mode', exact: true }).click();
    await page.screenshot({
      path: path.join(screenshots, 'overview-mobile-dark.png'),
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      'Real Settings browser: local save, shared proposal, exact owner handoff, mobile/dark and source-free requests PASS',
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
