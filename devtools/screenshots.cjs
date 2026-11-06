#!/usr/bin/env node
// Screenshot the panel and the card in the test box (devtools/testbox).
//
//   PLAYWRIGHT=/path/to/node_modules/playwright node devtools/screenshots.cjs [out-dir]
//   LANG_UI=cs ...   the same in another frontend language
//
// Logs in with the box's long-lived token, puts a dashboard with every card
// view on the default dashboard, and writes PNGs plus a list of console errors.
// Fails (exit 1) if the page logged an error that mentions the integration.
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const BASE = process.env.TESTBOX_URL || 'http://127.0.0.1:8324';
const OUT = path.resolve(process.argv[2] || 'screenshots');
const TOKEN = fs.readFileSync(path.join(__dirname, 'testbox', 'config', '.testbox_token'), 'utf8').trim();
const TABS = ['board', 'timeline', 'crops', 'plots', 'history', 'settings'];

const DASHBOARD = {
  views: [{
    title: 'Microgreens',
    type: 'masonry',
    cards: [
      { type: 'custom:ha-microgreens-card', view: 'tasks' },
      { type: 'custom:ha-microgreens-card', view: 'plot', plot_id: 'A2' },
      { type: 'custom:ha-microgreens-card', view: 'timeline', days: 21 },
      { type: 'custom:ha-microgreens-card', view: 'board', compact: true, show_tasks: false },
      { type: 'custom:microgreens-plot-card', plot_id: 'A5', title: 'Legacy plot card' },
    ],
  }],
};

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const errors = [];
  for (const [label, viewport] of [['desktop', { width: 1440, height: 960 }], ['mobile', { width: 390, height: 844 }]]) {
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: label === 'mobile' ? 2 : 1, colorScheme: 'light' });
    await ctx.addInitScript(([token, base, lang]) => {
      localStorage.setItem('hassTokens', JSON.stringify({ access_token: token, token_type: 'Bearer', expires_in: 1e9, hassUrl: base, clientId: `${base}/`, expires: Date.now() + 1e12, refresh_token: '' }));
      localStorage.setItem('ha_microgreens.tab', 'board');
      if (lang) localStorage.setItem('selectedLanguage', JSON.stringify(lang));
    }, [TOKEN, BASE, process.env.LANG_UI || '']);
    const page = await ctx.newPage();
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`${label}: ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`${label}: ${e.message}`));
    await page.goto(`${BASE}/ha-microgreens`, { waitUntil: 'networkidle' });
    await page.waitForSelector('ha-microgreens-panel .mg-tile', { timeout: 30000 });
    if (label === 'desktop') {
      await page.evaluate(async (cfg) => {
        const conn = document.querySelector('home-assistant').hass.connection;
        await conn.sendMessagePromise({ type: 'lovelace/config/save', config: cfg });
      }, DASHBOARD);
    }
    for (const tab of TABS) {
      await page.click(`ha-microgreens-panel .mg-tab[data-tab="${tab}"]`);
      await page.waitForTimeout(tab === 'settings' ? 1200 : 500);
      await page.screenshot({ path: path.join(OUT, `panel-${tab}-${label}.png`) });
    }
    await page.click('ha-microgreens-panel .mg-tab[data-tab="board"]');
    await page.click('ha-microgreens-panel .mg-tile[data-plot="A2"] [data-act="open"] >> nth=0');
    await page.waitForSelector('dialog.mg-dialog[open]');
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(OUT, `dialog-planting-${label}.png`) });
    await page.keyboard.press('Escape');
    await page.click('ha-microgreens-panel .mg-toolbar [data-act="sow"], ha-microgreens-panel .mg-fab >> visible=true');
    await page.waitForSelector('dialog.mg-dialog[open]');
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(OUT, `dialog-sow-${label}.png`) });
    await page.keyboard.press('Escape');
    await page.goto(`${BASE}/lovelace/0`, { waitUntil: 'networkidle' });
    await page.waitForSelector('ha-microgreens-card .mg-card-body', { timeout: 30000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(OUT, `dashboard-${label}.png`), fullPage: true });
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'console-errors.txt'), errors.join('\n') + '\n');
  const ours = errors.filter((e) => /microgreens/i.test(e));
  console.log(`screenshots in ${OUT}; ${errors.length} console errors (${ours.length} mention microgreens)`);
  if (ours.length) { console.log(ours.join('\n')); process.exit(1); }
}

main().catch((e) => { console.error(e); process.exit(1); });
