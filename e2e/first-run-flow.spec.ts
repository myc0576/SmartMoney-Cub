import { test, expect } from './fixtures/test-fixtures';

test.describe('First-run product flow: Overview -> Import toy sample -> Review & Insights', () => {
  test('guides a first-time user from empty Overview through offline toy import to populated Overview and en-US localization', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
    await mockWorkbenchApis(page);

    let importedRows: Record<string, unknown>[] = [];
    const toyTrades = [
      {
        round_trip_id: 'RT-TOY-1',
        trade_id: 'RT-TOY-1',
        symbol: 'TOY.CUB',
        name: 'Toy Cub A',
        exit_time: '2026-06-02 10:15:00',
        return_pct: 8.4,
        net_pnl: 839.6,
        currency: 'CNY',
        invalidation_price: 9.4,
        exit_price: 10.85,
      },
      {
        round_trip_id: 'RT-TOY-2',
        trade_id: 'RT-TOY-2',
        symbol: 'TOY.ALPHA',
        name: 'Toy Alpha',
        exit_time: '2026-06-04 14:40:00',
        return_pct: -4.96,
        net_pnl: -560.9,
        currency: 'CNY',
        invalidation_price: 21.6,
        exit_price: 21.3,
      },
      {
        round_trip_id: 'RT-TOY-3',
        trade_id: 'RT-TOY-3',
        symbol: 'TOY.CUB',
        name: 'Toy Cub A',
        exit_time: '2026-06-08 11:05:00',
        return_pct: 7.1,
        net_pnl: 788.5,
        currency: 'CNY',
        invalidation_price: 10.6,
        exit_price: 11.9,
      },
      {
        round_trip_id: 'RT-TOY-4',
        trade_id: 'RT-TOY-4',
        symbol: 'TOY.BETA',
        name: 'Toy Beta',
        exit_time: '2026-06-10 14:10:00',
        return_pct: 5.49,
        net_pnl: 667.5,
        currency: 'CNY',
        invalidation_price: 14.7,
        exit_price: 16.05,
      },
    ];

    await page.route('**/api/trader/trades/import', async (route) => {
      const payload = route.request().postDataJSON() || {};
      importedRows = Array.isArray(payload.rows) ? payload.rows : [];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          inserted_count: importedRows.length,
          updated_count: 0,
          safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
        }),
      });
    });

    await page.route('**/api/trader/analytics/summary*', async (route) => {
      const populated = importedRows.length > 0;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
          ledger_status: 'ok',
          counts: {
            closed_trades: populated ? 4 : 0,
            open_positions: 0,
            executions: populated ? 8 : 0,
            total_pnl: populated ? 1734.7 : 0,
          },
          summary: populated
            ? {
                trade_count: 4,
                win_count: 3,
                loss_count: 1,
                flat_count: 0,
                win_rate: 75,
                profit_factor: 4.09,
                profit_factor_note: '',
                total_net_pnl: 1734.7,
                total_fees: 45.3,
                avg_return_pct: 4.01,
                avg_win_pct: 7.0,
                avg_loss_pct: -4.96,
                avg_holding_days: 1.5,
                max_drawdown: -560.9,
                open_position_count: 0,
                sample_note: '4 synthetic toy round-trips',
                equity_curve: [
                  { date: '2026-06-02', cumulative_pnl: 839.6 },
                  { date: '2026-06-04', cumulative_pnl: 278.7 },
                  { date: '2026-06-08', cumulative_pnl: 1067.2 },
                  { date: '2026-06-10', cumulative_pnl: 1734.7 },
                ],
              }
            : {
                trade_count: 0,
                win_count: 0,
                loss_count: 0,
                flat_count: 0,
                win_rate: 0,
                profit_factor: null,
                profit_factor_note: '暂无数据',
                total_net_pnl: 0,
                total_fees: 0,
                avg_return_pct: 0,
                avg_win_pct: 0,
                avg_loss_pct: 0,
                avg_holding_days: 0,
                max_drawdown: 0,
                open_position_count: 0,
                sample_note: '离线测试空数据',
                equity_curve: [],
              },
        }),
      });
    });

    await page.route('**/api/trader/trades?*', async (route) => {
      const populated = importedRows.length > 0;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
          trades: populated ? toyTrades : [],
          open_positions: [],
          issues: [],
          ledger_status: 'ok',
          total: populated ? toyTrades.length : 0,
        }),
      });
    });

    await page.goto('/');
    await waitForAppReady(page);

    // 1. Empty Overview shows onboarding guide and actionable CTA, with no horizontal overflow.
    const onboarding = page.getByTestId('first-run-onboarding');
    await expect(onboarding).toBeVisible();
    const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(hasOverflow).toBe(false);

    // 2. Navigate to Import from the onboarding CTA.
    await onboarding.getByRole('button', { name: /导入成交/ }).click();
    await expect(page.locator('h1', { hasText: '数据导入' })).toBeVisible();

    // 3. Manual validation blocks empty submission cleanly without failing silently.
    await page.getByRole('button', { name: '补录', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('请填写日期');

    // 4. Load offline toy sample, verify editable rows, and confirm import.
    await page.getByTestId('load-toy-sample').click();
    await expect(page.getByText('校对识别结果（8 行）')).toBeVisible();
    await page.getByRole('button', { name: '确认导入', exact: true }).click();
    expect(importedRows.length).toBe(8);

    // 5. Post-import confirmation exposes direct navigation back to Overview and Insights.
    const nextSteps = page.getByTestId('import-next-steps');
    await expect(nextSteps).toBeVisible();
    await nextSteps.getByRole('button', { name: '查看总览仪表盘' }).click();

    // 6. Populated Overview hides onboarding card and shows toy KPIs & recent closes.
    await expect(page.getByTestId('first-run-onboarding')).toHaveCount(0);
    await expect(page.locator('.page')).toContainText('TOY.CUB');
    await expect(page.locator('.page')).toContainText('75%');

    // 7. Switching to English translates Overview headings and KPIs cleanly.
    await page.locator('#sidebar-locale-select').selectOption('en-US');
    await expect(page.locator('h1')).toHaveText('Overview');
    await expect(page.locator('.page')).toContainText('What needs attention today');
    await expect(page.locator('.page')).toContainText('Total Net P&L');
    await expect(page.locator('.page')).toContainText('Recent Closes');
    await expect(page.locator('.page')).not.toContainText('今天你需要关注什么');
  });

  test('empty Insights view exposes a direct import CTA', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
    await mockWorkbenchApis(page);
    await page.route('**/api/trader/insight/mistakes*', route => route.fulfill({ json: { rows: [], triggers: [] } }));
    await page.route('**/api/trader/insight/edges*', route => route.fulfill({ json: { rows: [] } }));
    await page.route('**/api/trader/insight/patterns*', route => route.fulfill({
      json: { profile: { sample_count: 0, account_count: 1, axes: {}, data_quality: 'descriptive', limitations: [] }, candidates: [] },
    }));

    await page.goto('/');
    await waitForAppReady(page);
    await page.getByRole('button', { name: '洞察', exact: true }).click();
    await expect(page.getByRole('button', { name: /去导入成交或示例/ })).toBeVisible();
    await page.getByRole('button', { name: /去导入成交或示例/ }).click();
    await expect(page.locator('h1', { hasText: '数据导入' })).toBeVisible();
  });

  test('assistant header stays single-line, assistant bubble never clips, and sidebar groups are unique at 1280/1440/1920', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
    await mockWorkbenchApis(page);
    await page.route('**/api/assistant/sessions/s-layout*', route => route.fulfill({
      json: {
        session: { session_id: 's-layout', title: '今日复盘 · 超长标题测试 Toy 示例', status: 'active', provider_id: 'alphatech', model: 'e2e-model', reasoning: 'off' },
        events: [
          { event_id: 1, seq: 1, kind: 'user_message', role: 'user', payload: { text: '复盘今天 TOY.ALPHA 越过失效价的那笔亏损' }, created_at: '2026-06-12T15:05:00+08:00' },
          { event_id: 2, seq: 2, kind: 'assistant_message', role: 'assistant', payload: { text: '### 复盘结论（只读证据）\n- **建议动作**：已生成 1 条 `challenger` 候选规则（需人工填写确认说明后才可晋级 `champion`）。' }, created_at: '2026-06-12T15:05:03+08:00' },
        ],
        safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
      },
    }));
    await page.route('**/api/assistant/sessions', route => route.fulfill({
      json: {
        sessions: [{ session_id: 's-layout', title: '今日复盘 · 超长标题测试 Toy 示例', status: 'active', updated_at: '2026-06-12T15:05:03+08:00' }],
        safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
      },
    }));

    for (const viewport of [
      { width: 1280, height: 800 },
      { width: 1440, height: 900 },
      { width: 1920, height: 1080 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto('/');
      await waitForAppReady(page);
      await expect(page.locator('.bubble.assistant')).toBeVisible();

      const metrics = await page.evaluate(() => {
        const assistant = document.querySelector('aside.assistant')!.getBoundingClientRect();
        const title = document.querySelector('.assistant-title')!.getBoundingClientRect();
        const btns = [...document.querySelectorAll('.assistant-head-btn')].map((el) => el.getBoundingClientRect());
        const bubble = document.querySelector('.bubble.assistant')!.getBoundingClientRect();
        const items = [...document.querySelectorAll('.bubble.assistant li')].map((el) => el.getBoundingClientRect());
        const sections = [...document.querySelectorAll('nav.sidebar .nav-section')].map((el) => (el.textContent || '').trim());
        return {
          assistantRight: assistant.right,
          titleHeight: title.height,
          maxBtnHeight: Math.max(...btns.map((b) => b.height)),
          maxBtnRight: Math.max(...btns.map((b) => b.right)),
          bubbleRight: bubble.right,
          maxItemRight: Math.max(...items.map((i) => i.right)),
          sections,
        };
      });

      expect(metrics.titleHeight).toBeLessThanOrEqual(24);
      expect(metrics.maxBtnHeight).toBeLessThanOrEqual(34);
      expect(metrics.maxBtnRight).toBeLessThanOrEqual(metrics.assistantRight + 1);
      expect(metrics.bubbleRight).toBeLessThanOrEqual(metrics.assistantRight + 1);
      expect(metrics.maxItemRight).toBeLessThanOrEqual(metrics.bubbleRight + 1);
      expect(new Set(metrics.sections).size).toBe(metrics.sections.length);
      expect(metrics.sections).toContain('数据');
    }

    // Verify overflow menu opens and contains secondary actions.
    await page.getByRole('button', { name: '更多会话操作' }).click();
    await expect(page.getByRole('menuitem', { name: '分叉会话' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: '展开助手' })).toBeVisible();
  });
});
