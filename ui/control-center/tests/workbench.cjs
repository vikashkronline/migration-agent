const { chromium } = require('playwright-core');
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const assets = path.resolve(__dirname, '../../../src/migration_agent/ui/static');
const token = 'offline-browser-fixture';
const screenshots = path.join(__dirname, 'artifacts');
fs.mkdirSync(screenshots, { recursive: true });
let revision = 'r1',
  artifact = 'digest-B',
  delayA = 0;
const commands = [];
const nodes = [
  {
    node_id: 'project',
    parent_id: null,
    label: 'Fixture project',
    kind: 'project',
    status: 'UNKNOWN',
    child_count: 0,
  },
  {
    node_id: 'work',
    parent_id: null,
    label: '2. Workflows & tasks',
    kind: 'group',
    status: 'WORK_PENDING',
    child_count: 2,
  },
  {
    node_id: 'a',
    parent_id: 'work',
    label: 'Documentation task',
    kind: 'task',
    status: 'APPROVAL_RECORDED',
    child_count: 0,
  },
  {
    node_id: 'b',
    parent_id: 'work',
    label: 'Migration task',
    kind: 'task',
    status: 'RECOVERY_REQUIRED',
    child_count: 0,
  },
  {
    node_id: 'knowledge',
    parent_id: null,
    label: 'Architecture reference',
    kind: 'reference',
    status: 'OBSERVED',
    child_count: 0,
  },
  {
    node_id: 'large',
    parent_id: null,
    label: 'Large generic work group',
    kind: 'group',
    status: 'WORK_PENDING',
    child_count: 1000,
  },
  ...Array.from({ length: 1000 }, (_, i) => ({
    node_id: 'generic-' + i,
    parent_id: 'large',
    label: 'Generic task ' + i,
    kind: 'task',
    status: 'PLANNED',
    child_count: 0,
  })),
].map((n) => ({
  ...n,
  complete_count: 0,
  task_count: n.node_id === 'work' ? 2 : n.node_id === 'large' ? 1000 : 0,
  dependencies: [],
  needs_attention: n.node_id === 'b',
  run_id: n.kind === 'task' ? 'run-1' : null,
}));
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname.startsWith('/api/')) {
    if (
      req.headers['x-session-token'] !== token &&
      !req.headers.cookie?.includes('session_token=' + token)
    ) {
      res.writeHead(401);
      res.end('{}');
      return;
    }
    const send = (data, status = 200) => {
      res.writeHead(status, {
        'Content-Type': 'application/json',
        'Set-Cookie': [
          'session_token=' + token + '; Path=/; HttpOnly; SameSite=Strict',
          'csrf_token=fixture-csrf; Path=/; SameSite=Strict',
        ],
      });
      res.end(JSON.stringify({ status: 'ok', data }));
    };
    if (url.pathname === '/api/v1/workbench/command') {
      let body = '';
      req.on('data', (d) => (body += d));
      req.on('end', () => {
        assert.equal(req.headers['x-csrf-token'], 'fixture-csrf');
        commands.push(JSON.parse(body));
        send(
          { operation_id: 'fixture-op', status: 'QUEUED', message: 'Guarded execution requested' },
          202,
        );
      });
      return;
    }
    if (url.pathname === '/api/v1/workbench/answer') {
      let body = '';
      req.on('data', (data) => (body += data));
      req.on('end', () => {
        const question = JSON.parse(body);
        const node = nodes.find((node) => node.node_id === question.node_id);
        send({
          project_id: 'fixture',
          node_id: node.node_id,
          revision,
          mode: 'recorded_evidence',
          answer: 'Matching recorded facts are listed below.',
          citations: [{ label: 'Status', text: node.status, node_id: node.node_id }],
        });
      });
      return;
    }
    let data;
    if (url.pathname === '/api/v1/health')
      data = {
        status: 'ok',
        checks: [{ name: 'python', status: 'pass', details: { actual: 'fixture' } }],
      };
    else if (url.pathname === '/api/v1/workbench')
      data = { project_id: 'fixture', actor: 'operator', assurance: 'MODE_B' };
    else if (url.pathname.endsWith('/tree')) {
      const parent = url.searchParams.get('parent'),
        query = url.searchParams.get('query'),
        kind = url.searchParams.get('kind'),
        attention = url.searchParams.get('attention') === '1';
      const selected = nodes.filter(
        (n) =>
          (!kind || n.kind === kind) &&
          (!attention || n.needs_attention) &&
          (query
            ? n.label.toLowerCase().includes(query.toLowerCase())
            : kind || attention
              ? true
              : n.parent_id === parent),
      );
      const offset = Number(url.searchParams.get('offset') || 0);
      data = {
        project_id: 'fixture',
        revision,
        cursor: 1,
        nodes: selected.slice(offset, offset + 100),
        ancestors: query || kind || attention ? [nodes[1], nodes[5]] : [],
        total: selected.length,
        next_offset: offset + 100 < selected.length ? offset + 100 : null,
      };
    } else if (url.pathname.endsWith('/detail')) {
      const node = nodes.find((n) => n.node_id === url.searchParams.get('node'));
      data = {
        project_id: 'fixture',
        revision,
        node,
        summary: 'Verified scoped evidence',
        run_id: node.kind === 'task' ? 'run-1' : null,
        changeset_id: node.kind === 'task' ? 'cs-' + revision : null,
        changeset_digest: node.kind === 'task' ? artifact : null,
        base_revision: 'base',
        policy_digest: 'policy',
        validation_digest: 'validation',
        files: ['src/example.ts'],
        diff: '<img src=x onerror=alert(1)>',
        evidence: [['BUILD', 'PASSED']],
        review_command: ['agent', 'approve', 'step-1'],
        actions:
          node.node_id === 'a'
            ? [
                {
                  kind: 'apply',
                  label: 'Apply approved exact artifact',
                  available: true,
                  reason: 'Core preflight',
                },
              ]
            : [],
        activity: [['stage / SUCCEEDED', 'Bound operation diagnostic']],
        diagram: node.node_id === 'knowledge' ? 'flowchart LR\n A[Application] --> B[Port]' : '',
        images: [],
        milestones: [
          ['Plan', 'RECORDED'],
          ['Apply result', node.status],
        ],
      };
      if (node.node_id === 'a' && delayA) {
        setTimeout(() => send(data), delayA);
        return;
      }
    } else if (url.pathname.endsWith('/diff')) {
      assert.equal(url.searchParams.get('artifact'), artifact);
      assert.equal(url.searchParams.get('index'), '0');
      data = {
        project_id: 'fixture',
        node_id: url.searchParams.get('node'),
        revision,
        changeset_digest: artifact,
        base_revision: 'base',
        path: 'src/example.ts',
        operation: 'MODIFY',
        file_mode: '0644',
        available: true,
        reason: '',
        hunks: [
          {
            old_start: 1,
            old_count: 1,
            new_start: 1,
            new_count: 1,
            lines: [
              { kind: 'remove', old_line: 1, new_line: null, text: 'const before = 1;\n' },
              { kind: 'add', old_line: null, new_line: 1, text: '<img src=x onerror=alert(1)>' },
            ],
          },
        ],
      };
    } else if (url.pathname.endsWith('/events'))
      data = {
        project_id: 'fixture',
        cursor: 1,
        changed: url.searchParams.get('revision') !== revision,
        more: false,
      };
    else {
      res.writeHead(409);
      res.end('{}');
      return;
    }
    send(data);
    return;
  }
  const file = url.pathname.includes('.')
    ? path.join(assets, path.basename(url.pathname))
    : path.join(assets, 'index.html');
  if (!fs.existsSync(file)) {
    res.writeHead(404);
    res.end();
    return;
  }
  res.writeHead(200, {
    'Content-Type': file.endsWith('.js')
      ? 'text/javascript'
      : file.endsWith('.css')
        ? 'text/css'
        : 'text/html',
    'Content-Security-Policy':
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:",
  });
  res.end(fs.readFileSync(file));
});
(async () => {
  let browser;
  try {
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const executablePath =
      process.env.CHROME_BIN ||
      (process.platform === 'win32'
        ? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
        : '/usr/bin/chromium');
    browser = await chromium.launch({ executablePath, headless: true });
    const page = await browser.newPage({ viewport: { width: 1024, height: 900 } });
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    const external = [];
    page.on('request', (r) => {
      if (!r.url().startsWith('http://127.0.0.1:')) external.push(r.url());
    });
    const base = 'http://127.0.0.1:' + server.address().port;
    const heading = (name) => page.getByRole('heading', { name, exact: true });
    const select = async (name) => {
      await page
        .getByRole('link', { name: new RegExp('^' + name) })
        .first()
        .click();
      await heading(name).waitFor();
    };
    await page.goto(base + '/#token=' + token);
    await heading('Fixture project').waitFor();
    assert(!page.url().includes(token));
    assert(await page.locator('aside').isVisible());
    assert(
      !(await page.getByRole('button', { name: 'Project navigation', exact: true }).isVisible()),
    );
    assert(!fs.readFileSync(path.join(assets, 'index.html'), 'utf8').includes('onload='));
    await page.getByRole('button', { name: 'Expand or collapse 2. Workflows & tasks' }).click();
    await select('Documentation task');
    await page.getByRole('link', { name: 'Artifacts', exact: true }).click();
    await page.getByText('Read-only proposed contents').click();
    assert.equal(await page.locator('main img').count(), 0);
    await page.getByRole('button', { name: 'Open read-only diff' }).click();
    await page.getByRole('heading', { name: 'MODIFY src/example.ts · mode 0644' }).waitFor();
    assert.equal(await page.locator('main img').count(), 0);
    await page.getByRole('button', { name: 'Split view', exact: true }).click();
    assert.equal(await page.locator('.diff-table.split').count(), 1);
    await page.screenshot({ path: path.join(screenshots, 'desktop-diff.png'), fullPage: true });
    await page.setViewportSize({ width: 375, height: 850 });
    await page.getByRole('button', { name: 'Split view', exact: true }).waitFor();
    assert(await page.getByRole('button', { name: 'Split view', exact: true }).isDisabled());
    assert.equal(await page.locator('.diff-table.split').count(), 0);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(screenshots, 'mobile-diff.png'), fullPage: true });
    await page.setViewportSize({ width: 1024, height: 900 });
    await page.getByRole('link', { name: 'Decision', exact: true }).click();
    assert(page.url().includes('artifact=digest-B'));
    await page.reload();
    await heading('Documentation task').waitFor();
    assert(!page.url().includes(token));
    await page.screenshot({ path: path.join(screenshots, 'desktop-decision.png'), fullPage: true });
    await page.getByRole('button', { name: 'Apply approved exact artifact' }).click();
    revision = 'r2';
    artifact = 'digest-C';
    await page
      .getByRole('dialog', { name: 'Confirm workflow action' })
      .waitFor({ state: 'hidden' });
    assert.equal(commands.length, 0);
    await page.getByRole('alert').filter({ hasText: 'pinned artifact' }).waitFor();
    await select('Documentation task');
    await page.getByRole('button', { name: 'Apply approved exact artifact' }).click();
    await page.getByRole('button', { name: 'Request action' }).click();
    await page.getByText(/fixture-op: QUEUED/).waitFor();
    assert.equal(commands.length, 1);
    assert.equal(commands[0].node_id, 'a');
    assert.equal(commands[0].changeset_id, 'cs-r2');
    assert.equal(commands[0].expected_revision, 'r2');
    delayA = 350;
    const delayed = page.waitForEvent('requestfailed', {
      predicate: (r) =>
        new URL(r.url()).pathname.endsWith('/detail') &&
        new URL(r.url()).searchParams.get('node') === 'a',
    });
    await page
      .getByRole('link', { name: /^Documentation task/ })
      .first()
      .click();
    await select('Migration task');
    await delayed;
    delayA = 0;
    assert.equal(await heading('Migration task').count(), 1);
    assert.equal(
      await page.getByRole('button', { name: 'Apply approved exact artifact' }).count(),
      0,
    );
    await page.setViewportSize({ width: 375, height: 850 });
    assert(!(await page.locator('aside').isVisible()));
    await page.screenshot({ path: path.join(screenshots, 'mobile-recovery.png'), fullPage: true });
    await page.getByRole('button', { name: 'Project navigation', exact: true }).click();
    const drawer = page.getByRole('dialog', { name: 'Project navigation' });
    await drawer.waitFor();
    assert(await drawer.isVisible());
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press('Tab');
      assert(
        await page.evaluate(
          () =>
            document.activeElement.closest('dialog')?.getAttribute('aria-label') ===
            'Project navigation',
        ),
      );
    }
    await page.keyboard.press('Escape');
    await drawer.waitFor({ state: 'hidden' });
    assert(!(await drawer.isVisible()));
    assert.equal(
      await page.evaluate(() => document.activeElement.textContent.trim()),
      'Project navigation',
    );
    await page.getByRole('button', { name: 'Project navigation', exact: true }).click();
    await drawer.waitFor({ state: 'visible' });
    await page.mouse.click(370, 650);
    await drawer.waitFor({ state: 'hidden' });
    assert(!(await drawer.isVisible()));
    await page.getByRole('button', { name: 'Project navigation', exact: true }).click();
    await drawer.waitFor({ state: 'visible' });
    await drawer.getByRole('link', { name: /^Documentation task/ }).click();
    await heading('Documentation task').waitFor();
    await drawer.waitFor({ state: 'hidden' });
    assert(!(await drawer.isVisible()));
    await page.getByRole('button', { name: 'Project navigation', exact: true }).click();
    await drawer.waitFor({ state: 'visible' });
    await page.setViewportSize({ width: 1024, height: 900 });
    await drawer.waitFor({ state: 'hidden' });
    assert.equal(await page.evaluate(() => document.body.style.overflow), '');
    await page.getByRole('button', { name: 'Attention', exact: true }).click();
    await page.getByText('1 matching recorded items.').first().waitFor();
    assert.equal(await page.getByRole('link', { name: /^Migration task/ }).count(), 1);
    await page.getByRole('button', { name: 'Attention', exact: true }).click();
    await heading('Documentation task').waitFor();
    await select('Architecture reference');
    await page.getByRole('button', { name: 'Render architecture diagram' }).click();
    await page.getByAltText('Architecture diagram for the selected reference').waitFor();
    assert.equal(await page.locator('main script, main foreignObject, main svg a').count(), 0);
    assert(
      await page
        .getByAltText('Architecture diagram for the selected reference')
        .evaluate((img) => img.complete && img.naturalWidth > 0),
    );
    await page.getByRole('link', { name: 'Platform health' }).click();
    await page.getByText(/python · pass/).waitFor();
    await page.getByRole('link', { name: 'Runs', exact: true }).click();
    await page.getByText(/1002 recorded tasks/).waitFor();
    await page.getByRole('link', { name: 'Return to selected item', exact: true }).click();
    const start = performance.now();
    await page.getByRole('button', { name: 'Expand or collapse Large generic work group' }).click();
    await page.getByRole('link', { name: /^Generic task 99 / }).waitFor();
    for (let pageNumber = 1; pageNumber < 10; pageNumber++) {
      await page
        .getByRole('button', { name: 'Load more in Large generic work group', exact: true })
        .click();
      await page
        .getByRole('link', { name: new RegExp('^Generic task ' + (pageNumber * 100 + 99) + ' ') })
        .waitFor();
    }
    await page.getByRole('link', { name: /^Generic task 999/ }).waitFor();
    const expansionMs = Math.round(performance.now() - start);
    await page.getByLabel('Find an item').first().fill('Generic task');
    await page.getByText('1000 matching recorded items.').first().waitFor();
    await page.getByRole('button', { name: 'Load more matches' }).first().click();
    await page.getByRole('link', { name: /^Generic task 199/ }).waitFor();
    await page.getByLabel('Find an item').first().fill('');
    await heading('Architecture reference').waitFor();
    for (const width of [375, 320]) {
      await page.setViewportSize({ width, height: 850 });
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
        false,
      );
    }
    await page.setViewportSize({ width: 1024, height: 900 });
    await select('Documentation task');
    await page.getByRole('link', { name: 'Decision', exact: true }).click();
    await page.goBack();
    await heading('Documentation task').waitFor();
    await page.getByRole('link', { name: 'Ask', exact: true }).last().click();
    await page.getByLabel('Question', { exact: true }).fill('What is the current status?');
    await page.getByRole('button', { name: 'Find recorded answer' }).click();
    await page.getByRole('heading', { name: 'Recorded evidence', exact: true }).waitFor();
    assert((await page.locator('cc-ask-page').textContent()).includes('APPROVAL_RECORDED'));
    await page.getByRole('button', { name: 'Light / dark' }).click();
    assert.equal(await page.locator('html').getAttribute('data-bs-theme'), 'dark');
    assert.equal(
      await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
      'rgb(33, 37, 41)',
    );
    await page.goto(base + '/projects/foreign/items/a');
    await page.getByRole('alert').filter({ hasText: 'Selected project' }).waitFor();
    assert.equal(await heading('Documentation task').count(), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      'Browser checks passed: AOT/CSP/offline, artifact invalidation, scoped command, selection race, drawer/focus/backdrop/resize, history, attention, diagnostics, strict diagram and 1000-task paging. Expansion: ' +
        expansionMs +
        ' ms.',
    );
  } finally {
    if (browser) await browser.close();
    server.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
