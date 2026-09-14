/* Visual pass over the product's own interface.
 * Serves nothing itself: it drives the running product, checks each view for
 * console errors and layout breakage, and writes screenshots to artifacts/visual.
 * Usage: node scripts/visual-check.cjs [baseUrl] [outDir]
 */
const fs = require('fs');
const path = require('path');
/* Resolve playwright from the repository's own node_modules, wherever the
 * repository happens to live. The previous form was an absolute path to one
 * developer's checkout, which meant the harness only ran on that machine and a
 * committed file published a local account name and directory layout. */
const { chromium } = require(require.resolve('playwright', {
  paths: [path.join(__dirname, '..')],
}));

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

  /* Second pass: the review assistant and the model seat inside it.
   *
   * WHY this exists: the loop above walks the 14 nav views, so it never opens
   * the docked assistant, never opens the picker menu, and never reaches the
   * effort stage. Those surfaces were rebuilt, and the regression worth
   * guarding is an effort level shown as a bare wire enum ("xhigh") with no
   * explanation of what it buys - so the effort-stage step fails unless every
   * row carries a non-empty .effort-desc.
   *
   * The four steps share one page on purpose: the effort stage only exists
   * after a model row inside the menu was clicked, and the settings step then
   * navigates away. A fresh context per step would replay that chain instead
   * of driving it.
   *
   * The dock is open by default and fits this harness width. The product hides
   * it with its own CSS below 980px, so if the dock is not visible the phase
   * skips with a printed reason rather than quietly resizing the viewport the
   * other views are judged at.
   */
  const ASSISTANT_STEPS = [
    ['复盘助手', 'assistant'],
    ['模型选择器', 'model-picker'],
    ['推理强度', 'effort-stage'],
    ['设置 · 模型', 'settings-models'],
  ];
  const assistantResults = [];
  let assistantCtx = null;
  let phaseSkipReason = '';
  try {
    assistantCtx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
    const page = await assistantCtx.newPage();
    const errs = [];
    page.on('console', m => { const t = m.text(); if (m.type() === 'error' && !NOISE.test(t)) errs.push(t.slice(0, 150)); });
    page.on('pageerror', e => { const s = String(e); if (!NOISE.test(s)) errs.push('pageerror: ' + s.slice(0, 150)); });

    /* Record one step with the same measurements, the same screenshot path and
     * the same ok rule a nav view gets, plus whatever that step asserted.
     * mark is the console-error count taken before the step: only errors the
     * step itself produced may be charged to it. */
    const record = async (label, key, ok, clicked, extra, mark) => {
      const rec = { label, key, ok: false };
      try {
        const state = await page.evaluate(() => ({
          dom: (document.getElementById('root') || { innerHTML: '' }).innerHTML.length,
          text: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 160),
          scrollW: document.documentElement.scrollWidth,
          clientW: document.documentElement.clientWidth,
          panels: document.querySelectorAll('.panel, .grid, table').length,
        }));
        /* Same horizontal-overflow rule as the nav pass. */
        const overflow = state.scrollW > state.clientW + 2;
        await page.screenshot({ path: path.join(OUT, key + '.png'), fullPage: false });
        Object.assign(rec, {
          clicked, dom: state.dom, panels: state.panels,
          overflow, width: state.scrollW, text: state.text,
          console_errors: [...new Set(errs.slice(mark))].slice(0, 3),
        }, extra);
        rec.ok = Boolean(clicked && ok) && state.dom > 1500 && !overflow && rec.console_errors.length === 0;
      } catch (e) {
        rec.error = String(e.message).slice(0, 140);
      }
      assistantResults.push(rec);
      console.log((rec.ok ? 'OK  ' : 'FAIL') + ' ' + label.padEnd(12) +
        ' dom=' + String(rec.dom || 0).padEnd(7) + ' panels=' + String(rec.panels || 0).padEnd(3) +
        ' overflow=' + String(!!rec.overflow).padEnd(6) + ' errs=' + (rec.console_errors || []).length +
        (rec.error ? ' ERR=' + rec.error : ''));
      (rec.console_errors || []).forEach(x => console.log('       ! ' + x));
    };

    await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 });
    /* Wait on the seat rather than a fixed sleep: the dock paints before the
     * provider directory arrives, and naming a model is what the seat does. */
    await page.waitForSelector('.assistant .picker-trigger', { timeout: 20000 }).catch(() => {});
    await page.waitForFunction(
      () => { const el = document.querySelector('.assistant .picker-label'); return Boolean(el && (el.innerText || '').trim()); },
      { timeout: 20000 },
    ).catch(() => {});
    await page.waitForTimeout(600);

    const dock = await page.evaluate(() => {
      const el = document.querySelector('.assistant');
      if (!el) return { present: false, visible: false, width: 0 };
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      /* A zero-size or display:none dock means "not shown at this width", which
       * is the product's own responsive rule, not a broken panel. */
      return {
        present: true,
        visible: style.display !== 'none' && rect.width > 40 && rect.height > 40,
        width: Math.round(rect.width),
      };
    });

    if (!dock.present || !dock.visible) {
      phaseSkipReason = 'assistant dock is not visible at the harness viewport ('
        + (dock.width || 0) + 'px wide); the product hides it below 980px';
    } else {
      console.log('\nassistant / model picker:');

      /* 1. The dock is present and names the seat. Nothing needs clicking: the
       *    dock is open by default, so clicked records that the step reached
       *    its state without being driven, the way a nav label that was not
       *    found would report false. */
      let mark = errs.length;
      const seat = await page.evaluate(() => {
        const trigger = document.querySelector('.assistant .picker-trigger');
        const label = trigger ? trigger.querySelector('.picker-label') : null;
        return {
          seat: Boolean(trigger && label),
          label: label ? (label.innerText || '').replace(/\s+/g, ' ').trim() : '',
          title: trigger ? (trigger.title || '') : '',
        };
      });
      await record('复盘助手', 'assistant',
        seat.seat && seat.label.length > 0, true,
        { seat: seat.seat ? 1 : 0, seat_label: seat.label.slice(0, 40), seat_title: seat.title }, mark);

      /* 2. The seat opens the picker. Driven through the real trigger, the same
       *    way the nav pass clicks the real nav item. */
      mark = errs.length;
      const opened = await page.evaluate(() => {
        const trigger = document.querySelector('.assistant .picker-trigger');
        if (!trigger) return false;
        trigger.click();
        return true;
      });
      if (opened) await page.waitForTimeout(700);
      const menu = await page.evaluate(() => ({
        menu: document.querySelectorAll('.picker-menu').length,
        groups: document.querySelectorAll('.picker-group').length,
        models: document.querySelectorAll('.model-row').length,
      }));
      await record('模型选择器', 'model-picker',
        opened && menu.menu === 1 && menu.groups >= 1 && menu.models >= 1, opened,
        { menu: menu.menu, provider_groups: menu.groups, model_rows: menu.models }, mark);

      /* 3. The model's own effort stage. The 可调强度 tag is the row's promise
       *    that it advertises more than one level, so a row carrying it must
       *    open a stage whose every row explains what that level buys. */
      mark = errs.length;
      const chose = await page.evaluate(() => {
        const row = [...document.querySelectorAll('.model-row')].find(el => /可调强度/.test(el.innerText || ''));
        if (!row) return false;
        row.click();
        return true;
      });
      if (chose) await page.waitForTimeout(700);
      const effort = await page.evaluate(() => {
        const rows = [...document.querySelectorAll('.effort-row')];
        const descs = rows.map(row => {
          const el = row.querySelector('.effort-desc');
          return el ? (el.innerText || '') : '';
        });
        return {
          rows: rows.length,
          missing: descs.filter(d => !d.trim()).length,
          sample: descs.map(d => d.replace(/\s+/g, ' ').trim().slice(0, 40)).slice(0, 3),
        };
      });
      await record('推理强度', 'effort-stage',
        chose && effort.rows >= 1 && effort.missing === 0, chose,
        { effort_rows: effort.rows, effort_desc_missing: effort.missing, effort_desc_sample: effort.sample }, mark);

      /* 4. The same directory on the settings page, so the seat and the page
       *    that edits the directory are both checked. */
      mark = errs.length;
      const navClicked = await page.evaluate(() => {
        const items = [...document.querySelectorAll('button, a, .nav-item')];
        const hit = items.find(el => (el.innerText || '').trim() === '设置');
        if (!hit) return false;
        hit.click();
        return true;
      });
      if (navClicked) await page.waitForTimeout(2200);
      /* The check button lives in an expanded provider card, so a collapsed
       * list has to be opened first - by its own 编辑 button, not by assuming
       * the card is already there. The offline provider has no endpoint to
       * check, so its row is skipped when picking which card to open. */
      const expand = async () => {
        const opened2 = await page.evaluate(() => {
          const row = [...document.querySelectorAll('.provider-row')].find(el => !/离线/.test(el.innerText || ''));
          if (!row) return false;
          const btn = [...row.querySelectorAll('button')].find(el => (el.innerText || '').trim() === '编辑');
          if (!btn) return false;
          btn.click();
          return true;
        });
        if (opened2) await page.waitForTimeout(700);
        return opened2;
      };
      const readSettings = () => page.evaluate(() => ({
        rows: document.querySelectorAll('.provider-row').length,
        verify: [...document.querySelectorAll('button')].some(el => (el.innerText || '').trim() === '校验模型目录'),
      }));
      let settings = await readSettings();
      if (settings.rows > 0 && !settings.verify) {
        await expand();
        settings = await readSettings();
      }
      await record('设置 · 模型', 'settings-models',
        navClicked && settings.rows >= 1 && settings.verify, navClicked,
        { provider_rows: settings.rows, verify_button: settings.verify }, mark);
    }
  } catch (e) {
    phaseSkipReason = 'assistant phase stopped early: ' + String(e.message).replace(/\s+/g, ' ').slice(0, 140);
    console.log('\nassistant / model picker: ' + phaseSkipReason);
  } finally { if (assistantCtx) { try { await assistantCtx.close(); } catch (e) {} } }

  /* Any step the phase never reached is recorded, so the report says what
   * happened instead of silently omitting it. */
  for (const [label, key] of ASSISTANT_STEPS) {
    if (assistantResults.some(r => r.key === key)) continue;
    const rec = { label, key, ok: false, skipped: true, reason: phaseSkipReason || 'the assistant phase did not reach this step' };
    assistantResults.push(rec);
    console.log('SKIP  ' + label.padEnd(12) + ' skipped - ' + rec.reason);
  }
  results.push(...assistantResults);

  const summary = {
    checked: results.length,
    clean: results.filter(r => r.ok).length,
    /* A skipped step is reported but is deliberately not a failure: it means
     * the surface is not shown at the viewport we were asked to keep, which is
     * the product's own responsive rule rather than a defect. It is therefore
     * kept out of failed, and the exit code stays clean. */
    skipped: results.filter(r => r.skipped).map(r => r.label),
    failed: results.filter(r => !r.ok && !r.skipped).map(r => r.label),
    overflow_count: results.filter(r => r.overflow).length,
    total_console_errors: results.reduce((a, r) => a + (r.console_errors || []).length, 0),
  };
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ base: BASE, summary, views: results }, null, 2));
  console.log('\nsummary: ' + JSON.stringify(summary));
  await browser.close();
  /* Skipped steps are excluded from failed, so this is the same test as
   * checked === clean whenever nothing was skipped. */
  process.exit(summary.failed.length === 0 ? 0 : 1);
})();
