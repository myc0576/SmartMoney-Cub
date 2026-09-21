import { test, expect } from '@playwright/test';

const safety = 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE';

test('JEV save is offline, test is explicit, and the key is cleared from the form', async ({ page }, testInfo) => {
  let configured = false;
  let probes = 0;
  await page.route('**/api/settings/jev**', async route => {
    const request = route.request();
    if (request.url().endsWith('/test')) probes++;
    else if (request.method() === 'POST') {
      expect(request.postDataJSON()).toEqual({ api_key: 'toy-browser-credential' });
      configured = true;
    }
    await route.fulfill({ json: { status: 'ok', configured, key_source: configured ? 'local' : 'none',
      connection: request.url().endsWith('/test') ? 'connected' : 'untested', model: 'jev-latest', safety } });
  });
  await page.goto('/test-fixtures/connections.html');
  await expect(page.getByLabel('JEV API 密钥')).toHaveAttribute('type', 'password');
  await page.getByLabel('JEV API 密钥').fill('toy-browser-credential');
  await page.getByRole('button', { name: '保存密钥' }).click();
  await expect(page.getByLabel('JEV API 密钥')).toHaveValue('');
  expect(probes).toBe(0);
  await page.getByRole('button', { name: '测试连接' }).click();
  await expect(page.getByText('本次测试通过', { exact: true })).toBeVisible();
  expect(probes).toBe(1);
  await page.screenshot({ path: testInfo.outputPath('jev-settings.png'), fullPage: true });
});

test('Agent read failures are visible and recoverable', async ({ page }, testInfo) => {
  let requests = 0;
  await page.route('**/api/agents', route => {
    requests++;
    return requests === 1 ? route.fulfill({ status: 503, json: { error: 'unavailable' } })
      : route.fulfill({ json: { agents: [{ agent_id: 'toy', label: 'Toy Agent', status: 'configured',
        config_path: 'toy-config.json', detail: 'Offline fixture' }], safety } });
  });
  await page.goto('/test-fixtures/connections.html?view=agents');
  await expect(page.getByRole('alert')).toContainText('无法读取 Agent 列表');
  await page.getByRole('button', { name: '刷新列表' }).click();
  await expect(page.getByText('Toy Agent', { exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('IME, double submit, folded tools, and stop preserve real streamed output', async ({ page }, testInfo) => {
  let created = 0;
  let cancelled = 0;
  await page.route('**/api/assistant/sessions**', async route => {
    const request = route.request();
    if (request.url().endsWith('/cancel')) {
      cancelled++;
      return route.fulfill({ json: { status: 'ok', safety } });
    }
    if (request.method() === 'POST') {
      created++;
      await new Promise(resolve => setTimeout(resolve, 250));
      return route.fulfill({ json: { session: { session_id: 'toy-session' } } });
    }
    return route.fulfill({ json: { sessions: [] } });
  });
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      if (String(input).endsWith('/messages')) {
        const encoder = new TextEncoder();
        return new Response(new ReadableStream({ start(controller) {
          const events = [
            { kind: 'tool_call', call_id: 'toy-call', name: 'toy_evidence', arguments: '{}' },
            { kind: 'tool_result', call_id: 'toy-call', result: { source: 'toy' } },
            { kind: 'tool_call', call_id: 'pending-call', name: 'toy_pending', arguments: '{}' },
            { kind: 'delta', text: '已收到的部分回复' },
          ];
          for (const event of events) controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
          init?.signal?.addEventListener('abort', () => controller.error(new DOMException('Stopped', 'AbortError')), { once: true });
        } }), { headers: { 'Content-Type': 'text/event-stream' } });
      }
      return original(input, init);
    };
  });
  await page.goto('/test-fixtures/connections.html?view=assistant');
  const input = page.getByRole('textbox');
  await input.fill('测试复盘');
  await input.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 229, isComposing: true });
  expect(created).toBe(0);
  await input.press('Enter');
  await input.press('Enter');
  await expect(page.getByText('已收到的部分回复', { exact: true })).toBeVisible();
  expect(created).toBe(1);
  await expect(page.locator('.tool-card[open]')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('assistant-running.png'), fullPage: true });
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByText('已停止接收 · 保留本轮内容', { exact: true })).toBeVisible();
  await expect(page.getByText('已收到的部分回复', { exact: true })).toBeVisible();
  expect(cancelled).toBe(1);
  await expect(page.locator('summary').filter({ hasText: 'toy_pending' })).toContainText('未返回结果');
  await expect(page.getByText('（进行中）', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('assistant-stopped.png'), fullPage: true });
});
