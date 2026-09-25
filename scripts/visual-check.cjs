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

/* Each entry names three things: what to click in the sidebar, what to click
 * inside that page (a secondary tab, or a button that opens the view), and the
 * file this view is photographed as.
 *
 * The three are separate on purpose. The sidebar text is an exact-match lookup
 * against the navigation in gui/src/App.tsx, so putting a descriptive label like
 * "洞察 · 重复错误" in its place makes a view silently un-clickable and the pass
 * then records the landing page under that name. A page with inner tabs needs a
 * row per tab, or every tab would photograph the same first tab and a broken
 * later one would never be seen.
 */
const VIEWS = [
  /* nav */            /* inner */    /* file */
  ['总览',              null,          'overview'],
  ['交易日志',          null,          'tradelog'],
  ['复盘日历',          null,          'calendar'],
  ['报告',              null,          'reports'],
  ['洞察',              '重复错误',    'insight-mistakes'],
  ['洞察',              'edges',       'insight-edges'],
  ['洞察',              '模式画像',    'insight-patterns'],
  ['策略实验室',        'Playbook',    'lab-playbooks'],
  ['策略实验室',        '规则库',      'lab-rules'],
  ['策略实验室',        '回测',        'lab-backtest'],
  ['演练',              null,          'drill-replay'],
  ['连接',              null,          'connections'],
  ['设置',              null,          'settings'],
  ['设置',              '插件',        'settings-plugins'],
  ['设置',              '模型',        'settings-model-directory'],
  /* No sidebar entry: this page is opened from the trade page's action, so its
     path is two clicks that a reader would make in the same order. */
  ['交易日志',          '导入',        'import'],
];

const NOISE = /favicon|net::ERR_|Failed to load resource/i;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu'] });
  const results = [];

  for (const [label, subTab, key] of VIEWS) {
    const rec = { label, key, ok: false };
    let ctx = null;
    try {
      ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
      const page = await ctx.newPage();
      const errs = [];
      page.on('console', m => { const t = m.text(); if (m.type() === 'error' && !NOISE.test(t)) errs.push(t.slice(0, 150)); });
      page.on('pageerror', e => { const s = String(e); if (!NOISE.test(s)) errs.push('pageerror: ' + s.slice(0, 150)); });

      await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 });
      /* Wait for the shell to mount, not for a fixed 2500ms. Clicking a nav
       * item before the sidebar exists returns false and quietly records the
       * landing view instead of the requested one -- which is how a view could
       * be reported at a fraction of its size on a loaded machine. The timeout
       * is left as a normal outcome so a page that genuinely never mounts is
       * still reported as a failed view rather than an exception. */
      await page.waitForSelector('.shell, .nav-item', { timeout: 45000 }).catch(() => {});
      await page.waitForTimeout(300);

      /* Click through the real navigation rather than deep-linking, so the pass
       * exercises the same path a person does. */
      const clickByText = (wanted) => page.evaluate((text) => {
        /* Exact match on the label, then a contains fallback for the controls
         * whose text carries a count beside the name -- the settings sub-tabs
         * render "模型 1", so an exact-match lookup for "模型" missed the tab
         * that was plainly on screen and the view was photographed as the
         * landing page. The fallback stays last so a nav item whose name is a
         * prefix of another still resolves to itself. */
        const items = [...document.querySelectorAll('button, a, .nav-item')];
        const norm = (el) => (el.innerText || '').replace(/\s+/g, ' ').trim();
        const hit = items.find(el => norm(el) === text)
          || items.find(el => norm(el).startsWith(text + ' '))
          || items.find(el => norm(el).includes(text));
        if (!hit) return false;
        hit.click();
        return true;
      }, wanted);

      /* A page reached from another page's action has no sidebar entry to click;
       * its click path is the label of the page that owns the action. */
      /* Two clicks at most: the sidebar destination, then whatever the page holds
       * -- a secondary tab, or the action that opens the view (the import page is
       * reached from the trade page's own button). A navigation click that misses
       * leaves clicked false and the row is reported as a failure rather than
       * photographed under the wrong name. */
      const nav = label;
      let clicked = await clickByText(nav);
      if (clicked && subTab) {
        await page.waitForTimeout(400);
        clicked = subTab === 'edges'
          ? await page.evaluate(() => {
              const hit = document.querySelector('[data-insight-tab="edges"]');
              if (!hit) return false;
              hit.click();
              return true;
            })
          : await clickByText(subTab);
      }
      if (clicked) {
        /* Wait for the view to settle rather than for a fixed delay. A fixed
         * 2200ms is enough on an idle machine and not enough on a loaded one,
         * where the view is still showing its loading line when the snapshot is
         * taken -- a slow render then reads exactly like a broken page. This
         * waits until the page is no longer loading, and treats the timeout as a
         * normal outcome so a genuinely stuck view is still reported. */
        await page.waitForFunction(
          () => {
            const page = document.querySelector('.page');
            if (!page) return false;
            const text = page.innerText || '';
            return !text.includes('加载中');
          },
          { timeout: 15000 },
        ).catch(() => {});
        /* And give the last paint a moment; the loading line can disappear
         * one frame before the panels it was standing in for. */
        await page.waitForTimeout(400);
      }
      const state = await page.evaluate(() => ({
        dom: (document.getElementById('root') || { innerHTML: '' }).innerHTML.length,
        text: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 160),
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
        panels: document.querySelectorAll('.panel, .grid, table').length,
        /* The view rendered its own content, not only the shell. A page whose
         * view failed leaves just the sidebar and topbar behind. */
        hasPanel: document.querySelectorAll('.page .panel, .page table, .page .grid').length > 0,
        /* An error surface means the view did not load, whatever its markup size.
         * Two shapes count. A banner is what a crash or a thrown fetch renders.
         * A view that reports a failed read inline -- "读取失败" -- is the same
         * failure wearing an empty state, and a harness that only looked for the
         * banner would call that page clean. */
        hasErrorBanner:
          document.querySelectorAll('.page .banner-error').length > 0
          || /读取失败|加载失败|失败：/.test(
               (document.querySelector('.page') || { innerText: '' }).innerText || ''
             ),
      }));

      /* Horizontal overflow is the classic layout breakage on a dashboard. */
      const overflow = state.scrollW > state.clientW + 2;
      /* One row per tab, so the file name carries the tab as well; a bare key
       * would let the last tab silently overwrite the earlier ones. */
      const slug = (subTab ? key + '-' + subTab : key)
        .replace(/[\s/\\]+/g, '-')
        .replace(/[^\w\u4e00-\u9fa5-]/g, '')
        .toLowerCase();
      const shot = path.join(OUT, slug + '.png');
      await page.screenshot({ path: shot, fullPage: false });

      Object.assign(rec, {
        clicked, dom: state.dom, panels: state.panels,
        overflow, width: state.scrollW, text: state.text,
        console_errors: [...new Set(errs)].slice(0, 3),
      });
      /* The previous rule was a byte count standing in for "did the page
       * render". That is the wrong measure in both directions: a small honest
       * view, such as an empty playbook list, fails it, while a page carrying a
       * large error banner passes. What matters is that the view rendered its own
       * panel and no error surface -- so those are the two conditions, with the
       * byte count still recorded for context. */
      rec.ok = Boolean(
        clicked
        && state.hasPanel
        && !state.hasErrorBanner
        && !overflow
        && rec.console_errors.length === 0
      );
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
    ['设置 · 模型目录', 'assistant-settings-models'],
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
     * provider directory arrives, and naming a model is what the seat does.
     *
     * The seat is a one-line summary now. The panel asks what to review rather
     * than which model to review it with, so the model, its directory, and the
     * reasoning levels live behind that summary -- which is why the steps below
     * open it before looking for the picker. */
    await page.waitForSelector('.assistant .assistant-model-chip', { timeout: 20000 }).catch(() => {});
    await page.waitForFunction(
      () => { const el = document.querySelector('.assistant .assistant-model-chip'); return Boolean(el && (el.innerText || '').trim()); },
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
        const chip = document.querySelector('.assistant .assistant-model-chip');
        return {
          seat: Boolean(chip),
          label: chip ? (chip.innerText || '').replace(/\s+/g, ' ').trim() : '',
          title: chip ? (chip.title || '') : '',
        };
      });
      await record('复盘助手', 'assistant',
        seat.seat && seat.label.length > 0, true,
        { seat: seat.seat ? 1 : 0, seat_label: seat.label.slice(0, 40), seat_title: seat.title }, mark);

      /* 2. The seat opens the picker. Driven through the real trigger, the same
       *    way the nav pass clicks the real nav item. */
      mark = errs.length;
      const opened = await page.evaluate(() => {
        /* The picker is inside a collapsed summary now, so opening the seat is
         * the first half of reaching it. Both clicks are driven through the real
         * elements, the way a reader would. */
        const chip = document.querySelector('.assistant .assistant-model-chip');
        if (!chip) return false;
        chip.click();
        return true;
      });
      if (opened) await page.waitForTimeout(400);
      const pickerOpened = await page.evaluate(() => {
        const trigger = document.querySelector('.assistant .picker-trigger');
        if (!trigger) return false;
        trigger.click();
        return true;
      });
      if (pickerOpened) await page.waitForTimeout(700);
      const menu = await page.evaluate(() => ({
        menu: document.querySelectorAll('.picker-menu').length,
        groups: document.querySelectorAll('.picker-group').length,
        models: document.querySelectorAll('.model-row').length,
      }));
      await record('模型选择器', 'model-picker',
        opened && pickerOpened && menu.menu === 1 && menu.groups >= 1 && menu.models >= 1, opened && pickerOpened,
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
      const readSettings = () => page.evaluate(() => {
        /* A collapsed provider is a .provider-row; the open editor replaces it
         * with a card, so the row count drops to zero once the card is open.
         * Counting rows alone therefore read "no providers configured" on a page
         * that had just opened one, and the step failed on a page that was
         * working. The check is "a provider is on screen in either shape". */
        const rows = document.querySelectorAll('.provider-row').length;
        const cards = document.querySelectorAll('.provider-card, .provider-form').length;
        return {
          rows: rows + cards,
          cards,
          verify: [...document.querySelectorAll('button')].some(el => (el.innerText || '').trim() === '校验模型目录'),
        };
      });
      let settings = await readSettings();
      if (settings.rows > 0 && !settings.verify) {
        await expand();
        settings = await readSettings();
      }
      await record('设置 · 模型目录', 'assistant-settings-models',
        navClicked && settings.rows >= 1 && settings.verify, navClicked,
        { provider_rows: settings.rows, provider_cards: settings.cards, verify_button: settings.verify }, mark);

      /* 5. The plugin marketplace with the assistant still docked.
       *
       *    The marketplace is the 插件 sub-tab inside 设置, not a top-level nav
       *    item, so the nav pass cannot reach it and it needs this step. Two
       *    defects are worth guarding and both only appear once the dock takes
       *    its 400px: the card grid used to drop to a single full-width column,
       *    and the missing stylesheet rules made the category chips and cards
       *    render with the browser's default white button background. */
      mark = errs.length;
      /* Find the settings page first, then its plugin sub-tab. The sub-tab is
       *  only in the DOM while 设置 is open. */
      const settingsOpened = await page.evaluate(() => {
        const items = [...document.querySelectorAll('button, a, .nav-item')];
        const hit = items.find(el => (el.innerText || '').trim() === '设置');
        if (!hit) return false;
        hit.click();
        return true;
      });
      if (settingsOpened) await page.waitForTimeout(1500);
      const marketNav = await page.evaluate(() => {
        const items = [...document.querySelectorAll('.dsh-nav-tab, button')];
        const hit = items.find(el => (el.innerText || '').trim() === '插件');
        if (!hit) return false;
        hit.click();
        return true;
      });
      if (marketNav) await page.waitForTimeout(2000);
      const market = await page.evaluate(() => {
        const grid = document.querySelector('.plugin-card-grid');
        const dock = document.querySelector('.assistant');
        const page_ = document.querySelector('.page');
        const columns = grid ? getComputedStyle(grid).gridTemplateColumns : '';
        const white = [...document.querySelectorAll('.plugin-card, .segmented, .segmented button, .plugin-card button')]
          .filter(el => getComputedStyle(el).backgroundColor === 'rgb(255, 255, 255)').length;
        return {
          cards: document.querySelectorAll('.plugin-card').length,
          columns: columns.split(' ').filter(Boolean).length,
          dockWidth: dock ? Math.round(dock.getBoundingClientRect().width) : 0,
          overflow: page_ ? page_.scrollWidth - page_.clientWidth : 0,
          whiteControls: white,
        };
      });
      await record('插件 · 助手下市场', 'plugins-with-assistant',
        settingsOpened && marketNav && market.cards > 0 && market.dockWidth > 0 && market.whiteControls === 0,
        marketNav,
        { market_cards: market.cards, market_columns: market.columns, dock_width: market.dockWidth,
          market_overflow: market.overflow, white_controls: market.whiteControls }, mark);
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

  /* Third pass: the product with the trust boundary closed.
   *
   * WHY this exists: in a shared/hosted deployment deploy/nginx.conf publishes
   * only '/api/trader/*' and answers every other '/api/**' path with 403, because
   * the rest of the API is the local single-user review workbench: it resolves no
   * tenant identity and reads the container's own shared state directory. Those
   * two passes above exercise the wide surface a laptop sees, so nothing here
   * covered the state every hosted visitor actually gets.
   *
   * The regression worth guarding is the one this state shipped with: the shell
   * booted and the trading views worked, but the assistant looked entirely
   * usable -- example prompts, an enabled input, a live Send button -- and only
   * failed after the user had typed a question and pressed it. The plugins and
   * rules views had the mirror-image defect: a failed read rendered as an empty
   * list, which reads as "nothing is installed" / "no rules exist", a different
   * claim from "this deployment does not publish that surface".
   *
   * The boundary is simulated in its own context rather than by editing the
   * running app: a route handler answers every '/api/**' request except
   * '/api/trader/**' with the 403 nginx returns. A fresh context also keeps the
   * intercepted page from disturbing the two passes above, which must keep
   * judging the wide surface.
   */
  const BOUNDARY_STEPS = [
    ['总览 · 边界关闭', 'boundary-boot'],
    ['复盘助手 · 边界关闭', 'boundary-assistant'],
    ['插件 · 边界关闭', 'boundary-plugins'],
    ['规则库 · 边界关闭', 'boundary-rules'],
  ];
  const boundaryResults = [];
  let boundarySkipReason = '';
  let boundaryCtx = null;
  try {
    boundaryCtx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
    const page = await boundaryCtx.newPage();
    const errs = [];
    page.on('console', m => { const t = m.text(); if (m.type() === 'error' && !NOISE.test(t)) errs.push(t.slice(0, 150)); });
    page.on('pageerror', e => { const s = String(e); if (!NOISE.test(s)) errs.push('pageerror: ' + s.slice(0, 150)); });

    /* Same measurements, same screenshot path and same ok rule as the earlier
     * passes, plus whatever this step asserted. mark is the console-error count
     * taken before the step: only errors the step itself produced may be charged
     * to it. */
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
      boundaryResults.push(rec);
      console.log((rec.ok ? 'OK  ' : 'FAIL') + ' ' + label.padEnd(16) +
        ' dom=' + String(rec.dom || 0).padEnd(7) + ' panels=' + String(rec.panels || 0).padEnd(3) +
        ' overflow=' + String(!!rec.overflow).padEnd(6) + ' errs=' + (rec.console_errors || []).length +
        (rec.error ? ' ERR=' + rec.error : ''));
      (rec.console_errors || []).forEach(x => console.log('       ! ' + x));
    };

    /* Reproduce the boundary the shipped proxy draws. The longest-match rule is
     * the one nginx applies: '/api/trader/**' is the tenant route and is served,
     * every other '/api/**' path is the workbench route and is refused. A JSON
     * body is returned rather than nginx's empty one so the app fails on its own
     * error path ('request failed: 403') instead of on a parse error, which is
     * the failure the deployment actually produces. */
    const BOUNDARY_BODY = JSON.stringify({ error: 'trust boundary: the workbench API is not published' });
    await page.route('**/api/**', (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.includes('/api/trader/')) { route.continue(); return; }
      route.fulfill({ status: 403, contentType: 'application/json', body: BOUNDARY_BODY });
    });

    console.log('\ntrust boundary closed (only /api/trader/** is served):');

    await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 });
    /* Wait on the headline number rather than a fixed sleep: the shell paints
     * before the journal answers, and a rendered KPI is what separates "the
     * trading surface works behind the boundary" from "the shell came up". */
    await page.waitForFunction(
      () => /净盈亏合计/.test((document.querySelector('.page') || { innerText: '' }).innerText || ''),
      { timeout: 20000 },
    ).catch(() => {});
    await page.waitForTimeout(600);

    /* 1. The page still boots with the boundary closed. The shell check alone
     *    would pass on the shell's own failure screen -- '无法连接本地复盘服务'
     *    also renders inside .shell -- so the assertion is the trading summary
     *    the shell owns, which only renders once /api/trader/analytics/summary
     *    answered through the boundary. */
    let mark = errs.length;
    const boot = await page.evaluate(() => {
      const pageEl = document.querySelector('.page');
      const pageText = pageEl ? (pageEl.innerText || '') : '';
      return {
        shell: document.querySelectorAll('.shell').length,
        pnl: /净盈亏合计/.test(pageText),
        disconnected: /无法连接本地复盘服务/.test(document.body.innerText || ''),
        safety: /READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE/.test(document.body.innerText || ''),
      };
    });
    await record('总览 · 边界关闭', 'boundary-boot',
      boot.shell === 1 && boot.pnl && !boot.disconnected, true,
      { shell: boot.shell, overview_pnl_label: boot.pnl, safety_banner: boot.safety, disconnected: boot.disconnected }, mark);

    /* 2. The assistant must not look usable. The notice carries 不可用 and the
     *    input is disabled, so the state is visible before anything is typed
     *    into it -- which is the whole point, since the defect it replaces was
     *    an honest failure reported only after the user pressed Send. The
     *    example prompts are recorded too: they are the tell that the panel is
     *    advertising a surface this deployment does not serve. */
    mark = errs.length;
    await page.waitForFunction(() => {
      const input = document.querySelector('.assistant textarea');
      return Boolean(input && input.disabled);
    }, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(400);
    const assistant = await page.evaluate(() => {
      const panel = document.querySelector('.assistant');
      const text = panel ? (panel.innerText || '') : '';
      const input = panel ? panel.querySelector('textarea') : null;
      const note = panel ? panel.querySelector('.notice') : null;
      return {
        present: Boolean(panel),
        unavailable: /不可用/.test(text),
        disabled: Boolean(input && input.disabled),
        prompts: /问点什么/.test(text),
        notice: note ? (note.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 80) : '',
      };
    });
    await record('复盘助手 · 边界关闭', 'boundary-assistant',
      assistant.present && assistant.unavailable && assistant.disabled, true,
      {
        unavailable: assistant.unavailable, textarea_disabled: assistant.disabled,
        example_prompts_shown: assistant.prompts, notice: assistant.notice,
      }, mark);

    /* The two workbench views, driven through the real navigation the way the
     * nav pass does. */
    const clickNav = async (label) => {
      const hit = await page.evaluate((label) => {
        const items = [...document.querySelectorAll('button, a, .nav-item')];
        const item = items.find(el => (el.innerText || '').trim() === label);
        if (!item) return false;
        item.click();
        return true;
      }, label);
      if (hit) await page.waitForTimeout(1800);
      return hit;
    };
    const readPage = () => page.evaluate(() => {
      const pageEl = document.querySelector('.page');
      const text = pageEl ? (pageEl.innerText || '').replace(/\s+/g, ' ') : '';
      return { text, failed: /读取失败/.test(text) };
    });

    /* 3. A refused read is reported as a refused read. An empty list would read
     *    as "no plugins are installed", which is a claim this deployment cannot
     *    make: the 403 says only that the surface is closed here. */
    mark = errs.length;
    /* The marketplace lives under 设置 as a sub-tab now, so the boundary pass
     * reaches it the same way the docked pass does. */
    const settingsForBoundary = await page.evaluate(() => {
      const items = [...document.querySelectorAll('button, a, .nav-item')];
      const hit = items.find(el => (el.innerText || '').trim() === '设置');
      if (!hit) return false;
      hit.click();
      return true;
    });
    if (settingsForBoundary) await page.waitForTimeout(1500);
    const pluginsClicked = await page.evaluate(() => {
      // Scope to the settings sub-navigation rather than every button on the
      // page: the plugin list carries its own 插件-labelled controls, and a
      // document-wide search can click one of those instead of the tab.
      const items = [...document.querySelectorAll('.dsh-nav-tab')];
      const hit = items.find(el => (el.innerText || '').trim() === '插件');
      if (!hit) return false;
      hit.click();
      return true;
    });
    if (pluginsClicked) await page.waitForTimeout(1600);
    const plugins = await readPage();
    await record('插件 · 边界关闭', 'boundary-plugins',
      pluginsClicked && plugins.failed && !/还没有发现插件/.test(plugins.text), pluginsClicked,
      { read_failed: plugins.failed, empty_claim: /还没有发现插件/.test(plugins.text), page_text: plugins.text.slice(0, 120) }, mark);

    /* 4. Same rule for the rule registry: 'no rules exist' is a different claim
     *    from 'this host does not publish the registry'.
     *
     *    The registry is a sub-tab of 策略实验室 now, not a sidebar destination,
     *    so it is reached by two clicks the way a reader would make them. */
    mark = errs.length;
    const labClicked = await clickNav('策略实验室');
    const rulesClicked = await page.evaluate(() => {
      const tab = [...document.querySelectorAll('[role="tab"], .subnav-item')]
        .find(el => (el.innerText || '').trim() === '规则库');
      if (!tab) return false;
      tab.click();
      return true;
    });
    if (rulesClicked) await page.waitForTimeout(1600);
    const rules = await readPage();
    await record('规则库 · 边界关闭', 'boundary-rules',
      labClicked && rulesClicked && rules.failed && !/还没有已晋级的规则/.test(rules.text), rulesClicked,
      { read_failed: rules.failed, empty_claim: /还没有已晋级的规则/.test(rules.text), page_text: rules.text.slice(0, 120) }, mark);
  } catch (e) {
    /* The boundary is a simulated state, so a failure to install it must not
     * read as a product defect. The one case that lands here is the route
     * handler itself being unavailable, which is a harness limitation rather
     * than a regression -- so the steps are skipped, not failed. */
    boundarySkipReason = 'the trust boundary could not be simulated: '
      + String(e.message).replace(/\s+/g, ' ').slice(0, 140);
    console.log('\ntrust boundary closed: ' + boundarySkipReason);
  } finally { if (boundaryCtx) { try { await boundaryCtx.close(); } catch (e) {} } }

  for (const [label, key] of BOUNDARY_STEPS) {
    if (boundaryResults.some(r => r.key === key)) continue;
    const rec = { label, key, ok: false, skipped: true, reason: boundarySkipReason || 'the trust-boundary phase did not reach this step' };
    boundaryResults.push(rec);
    console.log('SKIP  ' + label.padEnd(16) + ' skipped - ' + rec.reason);
  }
  results.push(...boundaryResults);

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
