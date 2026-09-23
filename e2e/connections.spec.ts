import { test, expect } from './fixtures/test-fixtures';

const manifest = {
  provider_id: 'local-statement-directory', name: 'Toy directory', description: 'Toy statements',
  official_links: [{ label: 'Official', url: 'https://example.invalid/docs' }],
  auth: { mode: 'local_files', fields: ['directory'], read_only: true, notes: 'CSV and JSON only; no broker login.' },
  supported_assets: ['stocks'], capabilities: ['read_events'], history: { precision: 'source_declared' },
  validation: { status: 'local_only', issues: [] },
};
const connected = { provider_id: manifest.provider_id, connected: true, revoked: false,
  credential_fields: ['directory'], scope: { allowed: true, status: 'verified' } };

test('partial sync remains visible after refreshing a connected catalogue', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/connections', route => route.fulfill({ json: { manifests: [manifest], statuses: [connected], accounts: [] } }));
  await page.route('**/api/trader/connections/*/sync', route => route.fulfill({ json: { status: 'ok', partial: true, imported_count: 2, errors: ['event_requires_mapping:toy'] } }));
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '连接', exact: true }).first().click();
  await expect(page.getByText(manifest.auth.notes)).toBeVisible();
  await page.locator('section').filter({ hasText: 'Toy directory' }).getByRole('button', { name: '同步', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('event_requires_mapping:toy');
});

test('directory auto-import is explicit and sent as a boolean', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/connections', route => route.fulfill({ json: { manifests: [manifest], statuses: [], accounts: [] } }));
  let body: any;
  await page.route('**/api/trader/connections/*/connect', async route => {
    body = route.request().postDataJSON();
    await route.fulfill({ json: { status: 'ok', connection: connected } });
  });
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '连接', exact: true }).first().click();
  await expect(page.getByText('Toy directory', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '连接', exact: true }).last().click();
  await expect(page.getByRole('checkbox')).not.toBeChecked();
  await page.getByRole('checkbox').check();
  await page.getByLabel('directory').fill('/toy/statements');
  await page.getByRole('button', { name: '验证并保存只读连接' }).click();
  await expect.poll(() => body?.config.watch_enabled).toBe(true);
  expect(body.credentials.directory).toBe('/toy/statements');
});

test('failed credential validation is visible without clearing the form', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/connections', route => route.fulfill({ json: { manifests: [manifest], statuses: [], accounts: [] } }));
  await page.route('**/api/trader/connections/*/connect', route => route.fulfill({ json: { status: 'error', scope: { issues: ['read_access_not_verified'] } } }));
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '连接', exact: true }).first().click();
  await expect(page.getByText('Toy directory', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '连接', exact: true }).last().click();
  await page.getByLabel('directory').fill('/toy/statements');
  await page.getByRole('button', { name: '验证并保存只读连接' }).click();
  await expect(page.getByRole('alert')).toContainText('read_access_not_verified');
  await expect(page.getByLabel('directory')).toHaveValue('/toy/statements');
});
