/* Fixed browser-v1 worker. No model-provided JavaScript or shell is evaluated. */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');

const request = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
console.log('browser-v1: loading verified automation module');
const { chromium } = require(request.playwright_entry);
const root = fs.realpathSync(request.build_root);
const output = fs.realpathSync(request.output_root);
const plan = request.plan;
let server, browser;
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.ico': 'image/x-icon', '.wasm': 'application/wasm' };

function fileFor(url) {
  const name = decodeURIComponent(new URL(url, 'http://127.0.0.1').pathname);
  if (name.includes('\\') || name.includes('\0') || name.split('/').includes('..')) throw Error('Unsafe path');
  let target = path.resolve(root, '.' + name);
  if (target !== root && !target.startsWith(root + path.sep)) throw Error('Unsafe path');
  for (let p = target; p !== root; p = path.dirname(p)) {
    if (fs.existsSync(p) && fs.lstatSync(p).isSymbolicLink()) throw Error('Linked path');
  }
  if (!fs.existsSync(target) || fs.statSync(target).isDirectory()) {
    if (path.extname(name)) return null;
    target = path.join(root, 'index.html');
  }
  if (/(^|[\/\\])(?:\.env|\.git|\.agent|.*\.(?:pem|key|p12))(?:[\/\\]|$)/i.test(target)) throw Error('Sensitive path');
  return target;
}

async function actions(page, items) {
  for (const action of items) {
    const element = page.locator(action.selector);
    if (action.kind === 'click') await element.click();
    else if (action.kind === 'fill') await element.fill(action.value);
    else if (action.kind === 'press') await element.press(action.value);
    else if (action.kind === 'select') await element.selectOption(action.value);
    else if (action.kind === 'check') await element.check();
    else throw Error('Unsupported action');
  }
}

async function assertions(page, items) {
  const failures = [];
  for (const assertion of items) {
    const locator = page.locator(assertion.selector || 'body');
    let pass = false;
    if (assertion.kind === 'visible') pass = await locator.isVisible();
    else if (assertion.kind === 'text') pass = (await locator.innerText()) === assertion.expected;
    else if (assertion.kind === 'value') pass = (await locator.inputValue()) === assertion.expected;
    else if (assertion.kind === 'count') pass = await locator.count() === Number(assertion.expected);
    else if (assertion.kind === 'url') {
      const url = new URL(page.url());
      pass = url.pathname + url.search + url.hash === assertion.expected;
    }
    if (!pass) failures.push({ rule_id: 'capability', description: `Expected ${assertion.kind} assertion failed for ${assertion.selector || 'route'}.` });
  }
  return failures;
}

async function measurements(page, rules) {
  return page.evaluate((geometry) => {
    const findings = [];
    const add = (rule_id, description) => findings.push({ rule_id, description });
    const visible = (element) => {
      const r = element.getBoundingClientRect();
      const s = getComputedStyle(element);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
    };
    if (document.documentElement.scrollWidth > innerWidth + 1) add('responsive', 'Document has unintended horizontal overflow.');
    const controls = Array.from(document.querySelectorAll('button,input,select,textarea,a[href],[role="button"]')).filter(visible);
    for (const element of controls) {
      const labelled = (element.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ');
      const name = element.getAttribute('aria-label') || labelled ||
        element.getAttribute('title') || (element.labels && Array.from(element.labels).map(l => l.textContent).join(' ')) ||
        ((element.tagName === 'BUTTON' || element.tagName === 'A') && (element.textContent || element.querySelector('img')?.alt)) ||
        (element.tagName === 'INPUT' && ['submit','button','reset'].includes(element.type) && element.value);
      if (!name || !String(name).trim()) add('accessibility', `Visible ${element.tagName.toLowerCase()} lacks an accessible name.`);
    }
    const rgb = (value) => {
      const m = value.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)$/);
      return m && (!m[4] || Number(m[4]) === 1) ? m.slice(1, 4).map(Number) : null;
    };
    const luminance = (color) => color.map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
      .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
    for (const rule of geometry) {
      const element = document.querySelector(rule.selector);
      const peer = rule.peer && document.querySelector(rule.peer);
      if (!element || !visible(element) || (rule.peer && (!peer || !visible(peer)))) {
        add(rule.rule_id, `Measurement requires visible elements: ${rule.selector}.`); continue;
      }
      const r = element.getBoundingClientRect();
      let value;
      if (rule.kind === 'gap') value = rule.axis === 'x' ? peer.getBoundingClientRect().left - r.right : peer.getBoundingClientRect().top - r.bottom;
      else if (rule.kind === 'align_left') value = Math.abs(r.left - peer.getBoundingClientRect().left);
      else if (rule.kind === 'font_size') value = parseFloat(getComputedStyle(element).fontSize);
      else if (rule.kind === 'target_size') value = Math.min(r.width, r.height);
      else if (rule.kind === 'contrast') {
        const fg = rgb(getComputedStyle(element).color);
        let ancestor = element, bg = null, unsupported = false;
        while (ancestor && !bg) {
          const style = getComputedStyle(ancestor);
          if (style.backgroundImage !== 'none' || style.opacity !== '1') unsupported = true;
          bg = rgb(style.backgroundColor); ancestor = ancestor.parentElement;
        }
        if (!fg || unsupported) { add(rule.rule_id, `Contrast needs investigation for ${rule.selector}.`); continue; }
        const a = luminance(fg), b = luminance(bg || [255,255,255]);
        value = (Math.max(a,b) + 0.05) / (Math.min(a,b) + 0.05);
      }
      if (!Number.isFinite(value) || value < rule.minimum || value > rule.maximum)
        add(rule.rule_id, `${rule.kind} for ${rule.selector} is ${value}; required range ${rule.minimum}..${rule.maximum}.`);
    }
    const focused = document.activeElement;
    if (focused && controls.includes(focused)) {
      const r = focused.getBoundingClientRect(), style = getComputedStyle(focused);
      if (r.bottom < 0 || r.top > innerHeight) add('accessibility', 'Keyboard focus is outside the visible viewport.');
    }
    const facts = JSON.stringify({ title: document.title, width: innerWidth, height: innerHeight,
      text: (document.body.innerText || '').slice(0, 10000),
      controls: controls.slice(0, 100).map(e => ({ tag: e.tagName, text: (e.textContent || '').trim().slice(0, 100),
        name: e.getAttribute('aria-label') || '', disabled: !!e.disabled, role: e.getAttribute('role') || '' })) });
    return { findings: findings.slice(0, 100), facts: facts.slice(0, 30000) };
  }, rules);
}

async function visit(base, item, viewport) {
  const context = await browser.newContext({ viewport: { width: Math.round(viewport.width / viewport.zoom), height: Math.round(viewport.height / viewport.zoom) },
    deviceScaleFactor: viewport.device_scale_factor * viewport.zoom, serviceWorkers: 'block', locale: 'en-US', timezoneId: 'UTC' });
  const permitted = new Set([base, ...plan.test_origins.map(o => o.replace(/\/$/, '')),
    ...(plan.source_url ? [plan.source_url.replace(/\/$/, '')] : [])]);
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === (plan.source_url || '').replace(/\/$/, '') && !['GET', 'HEAD'].includes(route.request().method()))
      return route.abort('blockedbyclient');
    if (url.protocol === 'data:' || permitted.has(url.origin)) return route.continue();
    return route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  const failures = [];
  page.on('pageerror', () => failures.push({ rule_id: 'interaction', description: 'Uncaught browser application error.' }));
  try {
    await page.goto(base + item.route, { waitUntil: 'networkidle', timeout: 10000 });
    await page.locator(item.ready_selector).waitFor({ state: 'visible' });
    await page.evaluate(() => document.fonts.ready);
    await actions(page, item.actions);
    failures.push(...await assertions(page, item.assertions));
    await page.keyboard.press('Tab');
    return { context, page, failures };
  } catch (_) {
    failures.push({ rule_id: 'interaction', description: 'Required route, readiness, action or assertion could not complete.' });
    return { context, page, failures };
  }
}

async function main() {
  console.log('browser-v1: starting staged application server');
  server = http.createServer((req, res) => {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405); res.end(); return; }
    try {
      const file = fileFor(req.url);
      if (!file) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      if (req.method === 'HEAD') res.end(); else fs.createReadStream(file).pipe(res);
    } catch (_) { res.writeHead(403); res.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  console.log('browser-v1: launching Chromium');
  browser = await chromium.launch({ executablePath: request.browser_path, headless: true, chromiumSandbox: request.chromium_sandbox !== false, timeout: 15000,
    args: ['--disable-background-networking', '--disable-component-update', '--disable-sync'] });
  const version = browser.version();
  console.log('browser-v1: Chromium ready');
  const images = [], journeys = [];
  if (request.phase === 'ui') {
    for (const origin of (plan.source_url ? ['source', 'target'] : ['target'])) {
      const cases = origin === 'source' && plan.source_cases.length ? plan.source_cases : plan.cases;
      for (const item of cases) for (const viewport of plan.viewports) {
        const case_key = `${item.id}--${viewport.id}`;
        if (!request.case_keys.includes(case_key)) continue;
        const target = origin === 'source' ? plan.source_url.replace(/\/$/, '') : base;
        const { context, page, failures } = await visit(target, item, viewport);
        try {
          const measured = await measurements(page, item.geometry);
          const aria = await page.locator('body').ariaSnapshot({timeout: 5000});
          measured.facts = JSON.stringify({dom: measured.facts, accessibility_snapshot: aria.slice(0,5000)}).slice(0,32700);
          const filename = `${case_key}--${origin}.png`;
          const size = page.viewportSize(), scale = viewport.device_scale_factor * viewport.zoom;
          let documentHeight = Math.max(size.height, await page.evaluate(() => document.documentElement.scrollHeight));
          if (documentHeight * scale > 16384 || size.width * documentHeight * scale * scale > 16000000) {
            measured.findings.push({rule_id:'states', description:'Full document exceeds the capture budget; declare bounded scroll-state coverage.'});
            documentHeight = size.height;
          }
          const clipHeight = plan.full_page ? documentHeight : size.height;
          const bytes = await page.screenshot({ path: path.join(output, filename), animations: 'disabled', fullPage: plan.full_page,
            clip: {x:0, y:0, width:size.width, height:clipHeight} });
          if (bytes.length > 5 * 1024 * 1024) throw Error('Screenshot limit exceeded');
          images.push({ case_key, origin, filename, viewport, capture_height_pixels: bytes.readUInt32BE(20), ready: failures.length === 0, facts: measured.facts,
            findings: [...failures, ...measured.findings].slice(0, 100),
            sha256: crypto.createHash('sha256').update(bytes).digest('hex') });
        } finally { await context.close(); }
      }
    }
  } else if (request.phase === 'e2e' && plan.e2e_enabled) {
    for (const item of plan.e2e_cases) {
      if (!request.case_keys.includes(item.id)) continue;
      const { context, failures } = await visit(base, item, plan.viewports[0]);
      journeys.push({ case_id: item.id, passed: failures.length === 0,
        details: failures.map(f => f.description).join(' ').slice(0, 2000) });
      await context.close();
    }
  } else throw Error('Unsupported browser phase');
  await browser.close(); browser = null;
  await new Promise(resolve => server.close(resolve)); server = null;
  fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({ browser_version: version, images, journeys }));
  console.log('Browser worker completed and closed its browser and server.');
}

main().catch(async (error) => {
  if (browser) await browser.close().catch(() => {});
  if (server) server.close();
  console.error('Browser worker failed; no passing evidence produced:', String(error.message).slice(0, 4000));
  process.exitCode = 1;
});
