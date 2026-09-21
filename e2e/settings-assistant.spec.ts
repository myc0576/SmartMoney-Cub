import { test, expect } from './fixtures/test-fixtures';

const safety = 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE';
const provider = { provider_id: 'toy', label: 'Toy provider', protocol: 'openai-chat', routable: true,
  has_key: true, key_status: 'configured', models: [{ id: 'toy-model', label: 'Toy model', reasoning_efforts: ['off'], default_effort: 'off' }] };
const session = { session_id: 'toy-session', title: 'Toy review', status: 'ready', provider_id: 'toy', model: 'toy-model', reasoning: 'off' };
const agent = { agent_id: 'codex', label: 'Codex CLI', status: 'detected', config_path: 'toy/config.toml', detected_version: null, detail: 'Toy integration', owned_keys: [] };

test.beforeEach(async ({ page, mockWorkbenchApis }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/meta', route => route.fulfill({ json: { providers: [provider], default_provider: 'toy', default_model: 'toy-model', default_reasoning: 'off', safety } }));
  await page.route('**/api/settings', route => route.fulfill({ json: { providers: [provider], catalog: [], protocols: [], defaults: { provider_id: 'toy', model: 'toy-model' }, safety } }));
  await page.route('**/api/audit*', route => route.fulfill({ json: { audits: [] } }));
  await page.route('**/api/doctor', route => route.fulfill({ json: { checks: [], safety } }));
  await page.route('**/api/agents', route => route.fulfill({ json: { agents: [agent], safety } }));
  await page.route('**/api/settings/jev', route => route.fulfill({ json: { has_key: false, has_local_key: false, key_source: 'none', connection_verified: false, model: 'jev-latest', safety } }));
  await page.route('**/api/assistant/sessions', route => route.fulfill({ json: route.request().method() === 'POST' ? { session } : { sessions: [] } }));
  await page.route('**/api/assistant/sessions/toy-session?*', route => route.fulfill({ json: { session, events: [] } }));
  // A controllable ReadableStream exercises the actual browser parser and UI,
  // without contacting a paid provider or using private journal records.
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    (window as any).__requests = 0;
    window.fetch = async (input, init) => {
      if (String(input).endsWith('/messages')) {
        (window as any).__requests++;
        const stream = new ReadableStream({ start(controller) {
          (window as any).__event = (event: unknown) => controller.enqueue(new TextEncoder().encode('data: ' + JSON.stringify(event) + '\n\n'));
          (window as any).__end = () => controller.close();
          init?.signal?.addEventListener('abort', () => controller.error(new DOMException('Stopped', 'AbortError')), { once: true });
        }});
        return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } });
      }
      return nativeFetch(input, init);
    };
  });
});

test('JEV leaves global navigation; connections and Agent management live in Settings', async ({ page }, testInfo) => {
  await page.goto('/');
  await expect(page.locator('.sidebar').getByRole('button', { name: 'Jev 引擎' })).toHaveCount(0);
  await page.locator('.sidebar').getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: 'JEV 连接', exact: true }).click();
  await expect(page.getByLabel('JEV API 密钥')).toHaveAttribute('type', 'password');
  await page.screenshot({ path: testInfo.outputPath('jev-settings.png') });
  await page.getByRole('button', { name: 'Agent 集成', exact: true }).click();
  await expect(page.getByText('Codex CLI', { exact: true })).toBeVisible();
  await expect(page.getByText(/后端诊断与模型真实性|四赛道离线审方问题包/)).toHaveCount(0);
});

test('JEV key save and explicit test are distinct; secret never goes into browser storage', async ({ page }) => {
  let saves = 0, probes = 0;
  await page.route('**/api/settings/jev', async route => {
    if (route.request().method() === 'POST') { saves++; expect(route.request().postDataJSON()).toEqual({ api_key: 'toy-secret' }); }
    await route.fulfill({ json: { has_key: saves > 0, has_local_key: saves > 0, key_source: saves ? 'local' : 'none', model: 'jev-latest', connection_verified: false, safety } });
  });
  await page.route('**/api/settings/jev/test', async route => { probes++; await route.fulfill({ json: { has_key: true, connection_verified: true, model_resolved: 'toy-jev', safety } }); });
  await page.goto('/');
  await page.locator('.sidebar').getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: 'JEV 连接', exact: true }).click();
  await page.getByLabel('JEV API 密钥').fill('toy-secret');
  await page.getByRole('button', { name: '保存密钥', exact: true }).click();
  await expect(page.getByLabel('JEV API 密钥')).toHaveValue('');
  expect(saves).toBe(1); expect(probes).toBe(0);
  await page.getByRole('button', { name: '测试连接', exact: true }).click();
  await expect(page.getByText('连接测试通过', { exact: false })).toBeVisible();
  expect(probes).toBe(1);
  expect(await page.evaluate(() => JSON.stringify(localStorage) + JSON.stringify(sessionStorage))).not.toContain('toy-secret');
});

test('duplicate sends cannot create parallel sessions while creation is pending', async ({ page }) => {
  let creates = 0;
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/assistant/sessions', async route => {
    if (route.request().method() === 'POST') { creates++; await pending; await route.fulfill({ json: { session } }); }
    else await route.fulfill({ json: { sessions: [] } });
  });
  await page.goto('/');
  const input = page.locator('.assistant-foot textarea');
  await input.fill('toy question');
  await input.press('Enter');
  await input.press('Enter');
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  await expect.poll(() => creates).toBe(1);
  release();
  await expect.poll(() => page.evaluate(() => (window as any).__requests)).toBe(1);
});

test('Chinese IME confirmation does not send', async ({ page }) => {
  await page.goto('/');
  const input = page.locator('.assistant-foot textarea');
  await input.fill('复盘');
  await input.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true });
  expect(await input.inputValue()).toBe('复盘');
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as any).__requests)).toBe(0);
});

test('tool details stay collapsed and Stop retains partial output while cancelling backend', async ({ page }, testInfo) => {
  let cancels = 0;
  await page.route('**/api/assistant/sessions/toy-session/cancel', async route => { cancels++; await route.fulfill({ json: { status: 'cancel_requested', safety } }); });
  await page.goto('/');
  await page.locator('.assistant-foot textarea').fill('toy question');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__requests)).toBe(1);
  await page.evaluate(() => {
    (window as any).__event({ kind: 'delta', text: '已读取两笔示例记录。' });
    (window as any).__event({ kind: 'tool_call', call_id: 'tool-1', name: 'journal_summary', arguments: '{}' });
  });
  await expect(page.locator('.tool-card')).not.toHaveAttribute('open');
  await expect(page.getByText('已读取两笔示例记录。')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('assistant-running.png') });
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByText('已读取两笔示例记录。')).toBeVisible();
  await expect(page.getByText('已停止', { exact: true })).toBeVisible();
  expect(cancels).toBe(1);
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible();
});

test('streamed errors stay visible and release the composer', async ({ page }) => {
  await page.goto('/');
  await page.locator('.assistant-foot textarea').fill('toy question');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__requests)).toBe(1);
  await page.evaluate(() => {
    (window as any).__event({ kind: 'delta', text: 'Partial toy answer' });
    (window as any).__event({ kind: 'error', error: 'Toy provider unavailable' });
    (window as any).__end();
  });
  await expect(page.getByText('Toy provider unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('Partial toy answer', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible();
});


test('failed session creation restores the draft and unlocks send', async ({ page }) => {
  await page.route('**/api/assistant/sessions', route => route.fulfill({
    status: route.request().method() === 'POST' ? 503 : 200,
    json: route.request().method() === 'POST' ? { error: 'Toy creation failed' } : { sessions: [] },
  }));
  await page.goto('/');
  await page.locator('.assistant-foot textarea').fill('retain my toy question');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByText('Toy creation failed', { exact: true })).toBeVisible();
  await expect(page.locator('.assistant-foot textarea')).toHaveValue('retain my toy question');
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled();
});

test('Agent preview does not mutate its badge; applying requires confirmation', async ({ page }) => {
  const calls: boolean[] = [];
  await page.route('**/api/agents/apply', async route => {
    calls.push(route.request().postDataJSON().dry_run);
    await route.fulfill({ json: { agent: { ...agent, status: 'configured' }, safety } });
  });
  await page.goto('/');
  await page.locator('.sidebar').getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: 'Agent 集成', exact: true }).click();
  await page.getByRole('button', { name: '预览', exact: true }).click();
  await expect(page.getByText(/预览完成：Codex CLI/)).toBeVisible();
  await expect(page.getByText('已检测到', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '应用', exact: true }).click();
  expect(calls).toEqual([true]);
  await page.getByRole('button', { name: '确认应用', exact: true }).click();
  await expect(page.getByText('已配置', { exact: true })).toBeVisible();
  expect(calls).toEqual([true, false]);
});

test('streaming does not pull a reader away from earlier messages', async ({ page }) => {
  await page.goto('/');
  await page.locator('.assistant-foot textarea').fill('toy question');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__requests)).toBe(1);
  await page.evaluate(() => (window as any).__event({ kind: 'delta', text: ('Toy line of evidence.\n\n').repeat(120) }));
  const body = page.locator('.assistant-body');
  await expect.poll(() => body.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
  await body.evaluate(node => { node.scrollTop = 0; node.dispatchEvent(new Event('scroll')); });
  await expect(page.getByRole('button', { name: /回到最新/ })).toBeVisible();
  await page.evaluate(() => (window as any).__event({ kind: 'delta', text: 'New evidence' }));
  await expect(page.getByText(/New evidence/)).toHaveCount(1);
  expect(await body.evaluate(node => node.scrollTop)).toBe(0);
  await page.getByRole('button', { name: /回到最新/ }).click();
  await expect.poll(() => body.evaluate(node => node.scrollHeight - node.scrollTop - node.clientHeight)).toBeLessThan(80);
});
