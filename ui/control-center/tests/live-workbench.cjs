const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_BIN, headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 375, height: 850 } });
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    const external = [];
    page.on('request', (r) => {
      if (!r.url().startsWith(process.env.GUI_TEST_ORIGIN)) external.push(r.url());
    });
    await page.goto(process.env.GUI_TEST_ORIGIN + '/#token=offline-live-fixture');
    await page.getByRole('heading', { name: 'project', exact: true }).waitFor();
    assert(!(await page.locator('aside').isVisible()));
    assert(await page.getByRole('button', { name: 'Project navigation', exact: true }).isVisible());
    assert(!page.url().includes('token='));
    assert(!(await page.getByRole('dialog', { name: 'Project navigation' }).isVisible()));
    await page.getByRole('link', { name: 'Runs', exact: true }).click();
    await page.getByRole('link', { name: 'Document generic interfaces', exact: true }).click();
    await page.getByRole('heading', { name: 'Document generic interfaces', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Checks', exact: true }).click();
    await page.getByText('No validation execution evidence recorded.').waitFor();
    await page.getByRole('link', { name: 'Decision', exact: true }).click();
    assert.equal(
      await page.getByRole('button', { name: 'Apply approved exact artifact' }).count(),
      0,
    );
    await page.reload();
    await page.getByRole('heading', { name: 'Document generic interfaces', exact: true }).waitFor();
    await page.getByRole('link', { name: 'Ask', exact: true }).last().click();
    await page.getByLabel('Question', { exact: true }).fill('What is the current status?');
    await page.getByRole('button', { name: 'Find recorded answer' }).click();
    await page.getByRole('heading', { name: 'Recorded evidence', exact: true }).waitFor();
    assert((await page.locator('cc-ask-page').textContent()).includes('PLANNED'));
    await page.getByRole('button', { name: 'Project navigation', exact: true }).click();
    await page
      .getByRole('dialog', { name: 'Project navigation' })
      .getByRole('link', { name: /1. Foundation/ })
      .click();
    await page
      .getByText('No verified project-readiness evidence is recorded for this group.')
      .waitFor();
    await page.getByRole('link', { name: 'Platform health' }).click();
    await page.getByText(/python · pass/).waitFor();
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log('Live loopback browser checks passed with canonical external state.');
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
