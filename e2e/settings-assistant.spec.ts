import { test, expect } from './fixtures/test-fixtures';
import type { Page } from '@playwright/test';

const provider = { provider_id: 'fixture', label: '测试模型', protocol: 'openai-chat', routable: true, has_key: true,
  models: [{ id: 'fixture-model', label: 'Fixture model', reasoning_efforts: ['off'], default_effort: 'off' }] };
const session = { session_id: 'ux-session', title: '测试复盘', provider_id: 'fixture', model: 'fixture-model', reasoning: 'off' };

async function prepare(page: Page, mode = 'stream') {
  await page.route('**/api/meta', r => r.fulfill({ json: { providers: [provider], default_provider: 'fixture', default_model: 'fixture-model', default_reasoning: 'off' } }));
  await page.route('**/api/settings', r => r.fulfill({ json: { providers: [provider], catalog: [], protocols: [], defaults: { provider_id: 'fixture', model: 'fixture-model', reasoning: 'off' } } }));
  await page.route('**/api/audit*', r => r.fulfill({ json: { audits: [] } }));
  await page.route('**/api/doctor', r => r.fulfill({ json: { checks: [] } }));
  await page.route('**/api/assistant/sessions**', r => r.fulfill({ json: { sessions: [session], session, events: [] } }));
  await page.route('**/api/settings/jev', r => r.fulfill({ json: { has_key: false, has_local_key: false, key_source: 'none', model_requested: 'jev-latest' } }));
  await page.route('**/api/agents', r => r.fulfill({ json: { agents: [ { agent_id: 'codex', label: 'Codex CLI', status: 'detected', detail: '测试配置，不写入真实文件' } ] } }));
  await page.addInitScript(({ mode }) => {
    const original = window.fetch.bind(window);
    (window as any).__uxSendCount = 0;
    window.fetch = async (input, init) => {
      if (!String(input).endsWith('/messages')) return original(input, init);
      (window as any).__uxSendCount++;
      if (mode === 'http-error') return new Response('{}', { status: 503 });
      return new Response(new ReadableStream({ start(controller) {
        (window as any).__uxEmit = (event: unknown) => controller.enqueue(new TextEncoder().encode('data: ' + JSON.stringify(event) + '\n\n'));
        init?.signal?.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')), { once: true });
      } }), { headers: { 'content-type': 'text/event-stream' } });
    };
  }, { mode });
  await page.goto('/');
  await expect(page.locator('.assistant-foot').getByRole('button', { name: '发送', exact: true })).toBeDisabled();
}

test.beforeEach(async ({ page, mockWorkbenchApis }) => { await mockWorkbenchApis(page); });

test('JEV and Agent integrations live in Settings, not the main sidebar', async ({ page }) => {
  await prepare(page);
  await expect(page.locator('.sidebar').getByRole('button', { name: /Jev 引擎/i })).toHaveCount(0);
  await page.locator('.sidebar').getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: 'JEV 连接', exact: true }).click();
  await expect(page.getByLabel('JEV API 密钥')).toHaveAttribute('type', 'password');
  await expect(page.getByRole('button', { name: '测试连接', exact: true })).toBeDisabled();
  await page.screenshot({ path: 'test-results/ux-jev-settings.png', fullPage: true });
  await page.getByRole('button', { name: 'Agent 集成', exact: true }).click();
  await expect(page.getByText('Codex CLI', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/ux-agent-settings.png', fullPage: true });
  await expect(page.getByText('四赛道离线审方问题包')).toHaveCount(0);
  await expect(page.getByText('后端诊断与模型真实性')).toHaveCount(0);
});

test('HTTP failure unlocks the composer and preserves a visible error', async ({ page }) => {
  await prepare(page, 'http-error');
  await page.locator('.assistant-foot textarea').fill('复盘测试');
  await page.locator('.assistant-foot').getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'HTTP 503' })).toBeVisible();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toHaveCount(0);
  await expect(page.getByText('本轮未完成', { exact: true })).toBeVisible();
});

test('IME Enter does not send; tool details are collapsed; stop preserves partial reply', async ({ page }) => {
  await prepare(page);
  const composer = page.locator('.assistant-foot textarea');
  await composer.fill('分析纪律');
  await composer.dispatchEvent('keydown', { key: 'Enter', isComposing: true });
  expect(await page.evaluate(() => (window as any).__uxSendCount)).toBe(0);
  await page.locator('.assistant-foot').getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByText('正在连接模型', { exact: true })).toBeVisible();
  await page.evaluate(() => (window as any).__uxEmit({ kind: 'tool_call', call_id: 'tool1', name: 'query_trades', arguments: '{}' }));
  await expect(page.getByText('正在读取证据', { exact: true })).toBeVisible();
  const tools = page.locator('.assistant-activity > .activity-tools');
  await expect(tools).not.toHaveAttribute('open');
  await page.evaluate(() => {
    (window as any).__uxEmit({ kind: 'tool_result', call_id: 'tool1', result: { count: 3 } });
    (window as any).__uxEmit({ kind: 'delta', text: '已找到三笔交易。' });
  });
  await expect(page.getByText('正在生成回复', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/ux-assistant-stream.png', fullPage: true });
  let cancelled = false;
  await page.route('**/api/assistant/sessions/ux-session/cancel', r => { cancelled = true; return r.fulfill({ json: { status: 'ok' } }); });
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByText('已停止', { exact: true })).toBeVisible();
  await expect(page.getByText('已找到三笔交易。', { exact: true })).toBeVisible();
  expect(cancelled).toBe(true);
});

test('session creation failure and repeated Enter cannot leave a locked or duplicate turn', async ({ page }) => {
  await prepare(page);
  await page.route('**/api/assistant/sessions', async r => {
    if (r.request().method() === 'GET') return r.fulfill({ json: { sessions: [] } });
    await new Promise(resolve => setTimeout(resolve, 150));
    return r.fulfill({ status: 500, json: { error: 'fixture-create-failure' } });
  });
  await page.reload();
  const composer = page.locator('.assistant-foot textarea');
  await composer.fill('创建失败测试');
  await expect(page.locator('.assistant-foot').getByRole('button', { name: '发送', exact: true })).toBeEnabled();
  let creates = 0;
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/api/assistant/sessions')) creates++; });
  await composer.press('Enter');
  await composer.press('Enter');
  await expect(page.getByRole('alert').filter({ hasText: 'fixture-create-failure' })).toBeVisible();
  expect(creates).toBe(1);
  await expect(page.getByRole('button', { name: '停止', exact: true })).toHaveCount(0);
});

test('a server error followed by done remains an error, never fake completion', async ({ page }) => {
  await prepare(page);
  await page.locator('.assistant-foot textarea').fill('错误测试');
  await page.locator('.assistant-foot').getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByText('正在连接模型', { exact: true })).toBeVisible();
  await page.evaluate(() => {
    (window as any).__uxEmit({ kind: 'delta', text: '保留的部分回复' });
    (window as any).__uxEmit({ kind: 'error', error: 'fixture-provider-error' });
    (window as any).__uxEmit({ kind: 'done' });
  });
  await expect(page.getByRole('alert').filter({ hasText: 'fixture-provider-error' })).toBeVisible();
  await expect(page.getByText('本轮未完成', { exact: true })).toBeVisible();
  await expect(page.getByText('保留的部分回复', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toHaveCount(0);
});

test('save does not test automatically or persist a JEV secret in the browser', async ({ page }) => {
  await prepare(page);
  let saved = false, tests = 0;
  await page.route('**/api/settings/jev', async r => {
    if (r.request().method() === 'POST') saved = true;
    return r.fulfill({ json: { has_key: saved, has_local_key: saved, key_source: saved ? 'local' : 'none', model_requested: 'jev-latest' } });
  });
  await page.route('**/api/settings/jev/test', r => {
    tests++;
    return r.fulfill({ json: { connected: true, checked_at: '2026-09-21T00:00:00Z', model_resolved: 'jev-fixture' } });
  });
  await page.locator('.sidebar').getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: 'JEV 连接', exact: true }).click();
  await page.getByLabel('JEV API 密钥').fill('fixture-browser-secret');
  await expect(page.getByRole('button', { name: '测试连接', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '保存密钥' }).click();
  await expect(page.getByLabel('JEV API 密钥')).toHaveValue('');
  expect(tests).toBe(0);
  expect(await page.evaluate(() => JSON.stringify(localStorage) + JSON.stringify(sessionStorage))).not.toContain('fixture-browser-secret');
  await page.getByRole('button', { name: '测试连接', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '连接测试成功' })).toBeVisible();
  expect(tests).toBe(1);
});

test('stopping while session creation is pending never starts model inference', async ({ page }) => {
  await prepare(page);
  await page.route('**/api/assistant/sessions', async r => {
    if (r.request().method() === 'GET') return r.fulfill({ json: { sessions: [] } });
    await new Promise(resolve => setTimeout(resolve, 400));
    return r.fulfill({ json: { session } });
  });
  await page.reload();
  await page.locator('.assistant-foot textarea').fill('准备期间停止');
  await page.locator('.assistant-foot').getByRole('button', { name: '发送', exact: true }).click();
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByText('已停止', { exact: true })).toBeVisible();
  await page.waitForTimeout(500); // Let the delayed creation response arrive.
  expect(await page.evaluate(() => (window as any).__uxSendCount)).toBe(0);
});

test('completed output is reconciled once, without duplicating or overflowing a bubble', async ({ page }) => {
  await prepare(page);
  await page.locator('.assistant-foot textarea').fill('完整回复');
  await page.locator('.assistant-foot').getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByText('正在连接模型', { exact: true })).toBeVisible();
  await page.route(/\/api\/assistant\/sessions\/ux-session(?:\?.*)?$/, r => r.fulfill({ json: { session, events: [
    { event_id: 1, kind: 'user_message', payload: { text: '完整回复' } },
    { event_id: 2, kind: 'assistant_message', payload: { text: '已完成证据整理。' } },
  ] } }));
  await page.evaluate(() => {
    (window as any).__uxEmit({ kind: 'delta', text: '已完成证据整理。' });
    (window as any).__uxEmit({ kind: 'done' });
  });
  await expect(page.getByText('本轮完成', { exact: true })).toBeVisible();
  await expect(page.getByText('已完成证据整理。', { exact: true })).toHaveCount(1);
  const body = await page.locator('.assistant-body').boundingBox();
  const bubble = await page.locator('.bubble.assistant').boundingBox();
  expect(bubble!.width).toBeLessThanOrEqual(body!.width);
});
