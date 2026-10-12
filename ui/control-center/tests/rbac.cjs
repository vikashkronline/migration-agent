const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_BIN, headless: true });
  const folder = path.resolve('../../reports/rbac-verification/browser');
  fs.mkdirSync(folder, { recursive: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(process.env.GUI_TEST_ORIGIN + '/?token=offline-rbac-browser-fixture');
    await page.getByRole('link', { name: 'Users and access', exact: true }).click();
    await page.getByRole('heading', { name: 'My access', exact: true }).waitFor();
    await page.getByLabel('Principal ID', { exact: true }).fill('new-reviewer');
    await page.getByLabel('Display name', { exact: true }).fill('New reviewer');
    const memberForm = page.locator('form').filter({ has: page.locator('#principal') });
    await memberForm.getByLabel('Reviewer', { exact: true }).check();
    await page.getByRole('button', { name: 'Prepare member change', exact: true }).click();
    await page
      .getByRole('heading', { name: 'Review proposed access change', exact: true })
      .waitFor();
    const command = await page.locator('#approval-command').inputValue();
    assert(command.includes('access') && command.includes('approve'));
    assert(command.includes('--state-dir') && command.includes('--trust-root'));
    assert(await page.getByRole('heading', { name: 'Current policy', exact: true }).isVisible());
    await page.screenshot({ path: path.join(folder, 'owner-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(folder, 'owner-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log(
      'RBAC browser passed: owner access, explicit reviewer proposal, complete terminal handoff, desktop/mobile rendering.',
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
