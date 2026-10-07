/* Real browser smoke test against a temporary local workspace and real HTTP demos. */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'tenantlens-browser-'));
  const port = Number(process.env.TENANTLENS_TEST_PORT || 18765);
  const base = `http://127.0.0.1:${port}`;
  const screenshots = path.join(root, 'docs', 'screenshots');
  await fs.mkdir(screenshots, { recursive: true });
  const server = spawn(process.env.PYTHON || 'python3', ['-S', '-m', 'tenantlens', 'serve', '--demo', '--port', String(port), '--state-dir', temp], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  const errors = [], requests = [], checks = [];
  const check = (name, condition) => { assert(condition, name); checks.push(name); };
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Panel startup timeout')), 10000);
      server.stdout.once('data', () => { clearTimeout(timer); resolve(); });
      server.once('exit', () => { clearTimeout(timer); reject(new Error('Panel failed to start')); });
    });
    browser = await chromium.launch({ headless: true,
      ...(process.env.TENANTLENS_CHROMIUM ? { executablePath: process.env.TENANTLENS_CHROMIUM } : {}),
      ...(process.env.TENANTLENS_BROWSER_ARGS ? { args: JSON.parse(process.env.TENANTLENS_BROWSER_ARGS) } : {}) });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, reducedMotion: 'reduce' });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    page.on('request', req => requests.push(req.url()));
    page.on('dialog', dialog => dialog.accept());
    await page.goto(base);
    await page.locator('.matrix').waitFor();
    check('three demo projects are available', await page.locator('#project-select option').count() === 3);
    check('no fabricated results before execution', await page.locator('.metric-violation strong').innerText() === '—\nHenüz çalıştırılmadı');
    const runs = [];
    for (const [mode, expected] of [['vulnerable', { PASS: 6, VIOLATION: 3, INCONCLUSIVE: 0, ERROR: 0 }], ['fixed', { PASS: 9, VIOLATION: 0, INCONCLUSIVE: 0, ERROR: 0 }], ['expired', { PASS: 4, VIOLATION: 0, INCONCLUSIVE: 5, ERROR: 0 }]]) {
      await page.locator('#project-select').selectOption(`demo-${mode}`);
      await page.getByRole('button', { name: 'Testi çalıştır', exact: true }).click();
      await page.locator('.run-strip').filter({ hasText: 'Tamamlandı' }).waitFor({ timeout: 15000 });
      const history = await context.request.get(`${base}/api/runs`).then(r => r.json());
      const run = await context.request.get(`${base}/api/runs/${history[0].id}`).then(r => r.json());
      assert.deepEqual(run.counts, expected); checks.push(`${mode}: expected real HTTP verdicts`); runs.push(run);
      if (mode === 'vulnerable') {
        await page.getByRole('button', { name: 'Bora’nın faturası / Ayşe kanıtını incele', exact: true }).click();
        await page.locator('.proof-panel').waitFor();
        check('cross-tenant proof is visible', (await page.locator('.proof-panel').innerText()).includes('unexpected_access') && (await page.locator('.proof-table').innerText()).includes('org-b'));
        await page.screenshot({ path: path.join(screenshots, 'matrix-dark.png'), fullPage: true });
        await page.getByRole('button', { name: 'Bulgular', exact: false }).first().click();
        check('three actionable findings', await page.locator('.finding').count() === 3);
        for (const kind of ['json', 'html']) {
          const pending = page.waitForEvent('download');
          await page.locator(`a[href$="report.${kind}"]`).click();
          const download = await pending;
          const content = await fs.readFile(await download.path(), 'utf8');
          check(`${kind} report downloads without credentials`, content.includes('unexpected_access') && !content.includes('tenantlens-demo-ayse-2026'));
          if (kind === 'json') assert.deepEqual(JSON.parse(content).counts, expected);
        }
        await page.getByRole('button', { name: 'İzin matrisi', exact: true }).click();
      }
    }
    await page.getByRole('button', { name: 'Hesaplar', exact: true }).click();
    check('expired identity is surfaced in accounts view', (await page.locator('.account-card').last().innerText()).includes('Kimlik belirsiz'));
    await page.getByRole('button', { name: 'Çalışma geçmişi', exact: true }).click();
    await page.getByRole('button', { name: `${runs[0].id.slice(0, 8)} çalışmasını aç`, exact: true }).click();
    await page.locator('.snapshot-banner').waitFor();
    check('history opens an immutable snapshot', await page.locator('.snapshot-banner').isVisible() && await page.getByRole('button', { name: 'Testi çalıştır', exact: true }).isDisabled());
    await page.getByRole('button', { name: 'Güncel tanımı aç', exact: true }).click();
    await page.getByRole('combobox', { name: 'Ayşe’nin faturası / Ayşe beklenen erişim', exact: true }).selectOption('deny');
    await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
    await page.getByRole('alert').waitFor();
    check('invalid baseline permission is blocked in the UI', (await page.getByRole('alert').innerText()).includes('baseline_account'));
    await page.getByRole('combobox', { name: 'Ayşe’nin faturası / Ayşe beklenen erişim', exact: true }).selectOption('allow');
    await page.getByRole('button', { name: 'Yeni proje', exact: true }).click();
    await page.getByLabel('Proje adı', { exact: true }).fill('Smoke · Düzenleme');
    await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Proje kaydedildi' }).waitFor();
    const createdId = await page.locator('#project-select').inputValue();
    await page.reload(); await page.locator('#project-select').waitFor();
    await page.locator('#project-select').selectOption(createdId);
    check('saved project survives a reload', (await page.locator('.topbar').innerText()).includes('Smoke · Düzenleme'));
    await page.getByRole('button', { name: 'Hesaplar', exact: true }).click();
    await page.getByRole('button', { name: 'Hesap ekle', exact: true }).click();
    check('account addition expands the authorization matrix', await page.locator('.account-card').count() === 4);
    await page.getByRole('button', { name: 'İzin matrisi', exact: true }).click();
    await page.getByRole('button', { name: 'Kaynak ekle', exact: true }).click();
    await page.getByRole('button', { name: 'Tanımı uygula', exact: true }).click();
    await page.getByRole('dialog').waitFor({ state: 'hidden' });
    check('resource editor validates and adds a matrix row', await page.locator('.matrix tbody tr').count() === 4);
    await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Proje kaydedildi' }).waitFor();
    await page.getByRole('button', { name: 'Proje tanımı', exact: true }).click();
    const pending = page.waitForEvent('download');
    await page.getByRole('button', { name: 'JSON', exact: true }).click();
    const exported = JSON.parse(await fs.readFile(await (await pending).path(), 'utf8'));
    check('project export contains environment references only', exported.accounts.length === 4 && exported.accounts.every(a => a.auth_env.startsWith('TENANTLENS_') && !a.token));
    await page.getByRole('button', { name: 'Projeyi sil', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Proje silindi' }).waitFor();
    check('project deletion preserves all previous run history', (await context.request.get(`${base}/api/runs`).then(r => r.json())).length === 3);
    await page.locator('input[type=file]').setInputFiles({ name: 'import.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ ...exported, id: 'browser-import', name: 'İçe aktarılan proje' })) });
    await page.getByRole('status').filter({ hasText: 'JSON doğrulandı' }).waitFor();
    check('JSON import is a validated unsaved draft', await page.locator('#project-select').inputValue() === 'browser-import');
    await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Proje kaydedildi' }).waitFor();
    await page.locator('#project-select').selectOption('demo-fixed');
    await page.getByRole('button', { name: 'Açık temaya geç', exact: true }).click();
    await page.getByRole('button', { name: 'İzin matrisi', exact: true }).click();
    await page.screenshot({ path: path.join(screenshots, 'matrix-light.png'), fullPage: true });
    check('theme switch is persisted', await page.evaluate(() => localStorage.getItem('tenantlens-theme')) === 'light');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(screenshots, 'matrix-mobile.png'), fullPage: true });
    check('mobile page has no global horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(screenshots, 'matrix-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1050 });
    // A stop request must produce cancellation rather than completion.
    await page.getByRole('button', { name: 'Testi çalıştır', exact: true }).click();
    await page.getByRole('button', { name: 'Durdur', exact: true }).click();
    await page.locator('.run-strip').filter({ hasText: 'Durduruldu' }).waitFor();
    check('active run can be cancelled', (await page.locator('.run-strip').innerText()).includes('Durduruldu'));
    check('panel issues only same-origin requests', requests.every(url => url.startsWith(base + '/') || url === base));
    // The intentionally rejected validation request may create one network console error.
    check('no browser exceptions or CSP failures', errors.every(e => e.includes('400 (Bad Request)')));
    console.log(JSON.stringify({ checks: checks.length, passed: checks, browser: await browser.version(), external_requests: requests.filter(url => !url.startsWith(base)), errors }, null, 2));
  } finally {
    if (browser) await browser.close();
    server.kill('SIGINT');
    await new Promise(resolve => { if (server.exitCode !== null) resolve(); else { server.once('exit', resolve); setTimeout(() => { server.kill('SIGKILL'); resolve(); }, 3000).unref(); } });
    await fs.rm(temp, { recursive: true, force: true });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
