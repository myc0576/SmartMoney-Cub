/* Visual pass over the product's own interface.
 * Serves nothing itself: it drives the running product, checks each view for
 * console errors and layout breakage, and writes screenshots to artifacts/visual.
 * Usage: node scripts/visual-check.cjs [baseUrl] [outDir]
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('/Users/myc/Smartmoney-Cub/node_modules/playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:8800';
const OUT = process.argv[3] || path.join(__dirname, '..', 'artifacts', 'visual');

/* Each entry: the nav label as the user sees it, and the view it opens. */
const VIEWS = [
  ['总览', 'overview'],
  ['交易日志', 'tradelog'],
  ['复盘日历', 'calendar'],
  ['绩效分析', 'analytics'],
  ['规则库', 'rules'],
  ['数据导入', 'import'],
  ['插件', 'plugins'],
  ['设置', 'settings'],
  ['报告', 'reports'],
  ['Playbook', 'playbooks'],
  ['回测', 'backtest'],
  ['K 线回放', 'replay'],
  ['自营账户', 'propfirm'],
  /* Labels below come from the navigation in gui/src/App.tsx; a label here that
   * does not match that file makes the view silently un-clickable. */
  ['成交台账', 'trades'],
];

const NOISE = /favicon|net::ERR_|Failed to load resource/i;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu'] });
  const results = [];

  for (const [label, key] of VIEWS) {
    const rec = { label, key, ok: false };
    let ctx = null;
    try {
      ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
      const page = await ctx.newPage();
      const errs = [];
      page.on('console', m => { const t = m.text(); if (m.type() === 'error' && !NOISE.test(t)) errs.push(t.slice(0, 150)); });
      page.on('pageerror', e => { const s = String(e); if (!NOISE.test(s)) errs.push('pageerror: ' + s.slice(0, 150)); });

      await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(2500);

      /* Click through the real navigation rather than deep-linking, so the pass
       * exercises the same path a person does. */
      const clicked = await page.evaluate((label) => {
        const items = [...document.querySelectorAll('button, a, .nav-item')];
        const hit = items.find(el => (el.innerText || '').trim() === label);
        if (!hit) return false;
        hit.click();
        return true;
      }, label);
      if (clicked) await page.waitForTimeout(2200);

      const state = await page.evaluate(() => ({
        dom: (document.getElementById('root') || { innerHTML: '' }).innerHTML.length,
        text: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 160),
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
        panels: document.querySelectorAll('.panel, .grid, table').length,
      }));

      /* Horizontal overflow is the classic layout breakage on a dashboard. */
      const overflow = state.scrollW > state.clientW + 2;
      const shot = path.join(OUT, key + '.png');
      await page.screenshot({ path: shot, fullPage: false });

      Object.assign(rec, {
        clicked, dom: state.dom, panels: state.panels,
        overflow, width: state.scrollW, text: state.text,
        console_errors: [...new Set(errs)].slice(0, 3),
      });
      rec.ok = clicked && state.dom > 1500 && !overflow && rec.console_errors.length === 0;
    } catch (e) {
      rec.error = String(e.message).slice(0, 140);
    } finally { if (ctx) { try { await ctx.close(); } catch (e) {} } }
    results.push(rec);
    console.log((rec.ok ? 'OK  ' : 'FAIL') + ' ' + label.padEnd(12) +
      ' dom=' + String(rec.dom || 0).padEnd(7) + ' panels=' + String(rec.panels || 0).padEnd(3) +
      ' overflow=' + String(!!rec.overflow).padEnd(6) + ' errs=' + (rec.console_errors || []).length +
      (rec.error ? ' ERR=' + rec.error : ''));
    (rec.console_errors || []).forEach(x => console.log('       ! ' + x));
  }

  const summary = {
    checked: results.length,
    clean: results.filter(r => r.ok).length,
    failed: results.filter(r => !r.ok).map(r => r.label),
    overflow_count: results.filter(r => r.overflow).length,
    total_console_errors: results.reduce((a, r) => a + (r.console_errors || []).length, 0),
  };
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ base: BASE, summary, views: results }, null, 2));
  console.log('\nsummary: ' + JSON.stringify(summary));
  await browser.close();
  process.exit(summary.checked === summary.clean ? 0 : 1);
})();
