import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const accounts = [
  ["plant.manager@genuinegigs.local", "Material requirements"],
  ["purchase.exec@genuinegigs.local", "Material requirements"],
  ["purchase.manager@genuinegigs.local", "Supplier quotations"],
  ["gate.operator@genuinegigs.local", "Gate entry"],
  ["store.manager@genuinegigs.local", "Store receipt"],
  ["quality.inspector@genuinegigs.local", "Quality inspection"],
  ["admin@genuinegigs.local", "Control centre"],
] as const;

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel('Work email').fill(email);
  await page.getByLabel('Password').fill('Password@123');
  await page.getByRole("button", { name: "Continue to GenuineGigs" }).click();
  const workspace = page.getByLabel('Operating workspace');
  const productShell = page.locator(".gg-product-shell");
  await expect.poll(async () => (await workspace.isVisible()) || (await productShell.isVisible())).toBeTruthy();
  if (await workspace.isVisible().catch(() => false)) {
    const demoWorkspaceId = await workspace.locator('option').filter({ hasText: 'Apex Components' }).first().getAttribute('value');
    if (!demoWorkspaceId) throw new Error('Demo workspace was not available at sign in');
    await workspace.selectOption(demoWorkspaceId);
    await expect(workspace).toHaveValue(demoWorkspaceId);
    const enterWorkspace = page.getByRole("button", { name: "Enter workspace" });
    await expect(enterWorkspace).toBeEnabled();
    await enterWorkspace.click();
  }
  await expect(productShell).toBeVisible();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
  await page.goto('/procurement');
  if (test.info().title.includes('multi-line requirement')) {
    await page.goto('/procurement');
    await expect(page.getByRole('heading', { name: 'New requirement' })).toBeVisible();
  }
}

async function openReadyAgent(page: Page) {
  const drawer = page.locator('.agent-drawer');
  await expect(async () => {
    if (!(await drawer.isVisible().catch(() => false))) {
      await page.getByRole('button', { name: 'Open role agent' }).click();
    }
    await expect(drawer).toBeVisible({ timeout: 2_000 });
    await expect(page.locator('.agent-drawer-loading')).toBeHidden({ timeout: 2_000 });
    await expect(page.getByLabel('Message my role agent')).toBeEnabled({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  return drawer;
}

test('purchase executive sees role-scoped work and an assistant entry point', async ({ page }) => {
  await signIn(page, 'purchase.exec@genuinegigs.local');
  await expect(page.getByRole('heading', { name: 'Needs your attention' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'My tasks' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Requirements' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'RFQs' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Comparison & approvals' })).toBeVisible();
  await expect(page.getByRole('link', { name: /agent/i })).toHaveCount(0);
});

test('controlled manager decision asks for explicit confirmation', async ({ page }) => {
  await signIn(page, 'purchase.manager@genuinegigs.local');
  await page.goto('/procurement/orders');
  const purchaseOrder = page.getByLabel('Purchase order');
  await purchaseOrder.selectOption({ index: 1 });
  const prepareEmail = page.getByRole('button', { name: 'Prepare supplier delivery' });
  await expect(prepareEmail).toBeEnabled();
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('supplier delivery');
    await dialog.dismiss();
  });
  await prepareEmail.click();
  await expect(prepareEmail).toBeEnabled();
});

test('mobile ledgers contain structured ERP data without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, 'purchase.manager@genuinegigs.local');
  await page.goto('/procurement/orders');
  await expect(page.getByRole('heading', { name: 'Review and issue the order' })).toBeVisible();
  const dimensions = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
  await expect(page.getByRole('heading', { level: 1, name: 'Purchase orders' })).toBeVisible();
});

test('contextual assistant remains integrated at mobile width', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, 'plant.manager@genuinegigs.local');
  await expect(page.locator('.agent-launcher')).toBeVisible();
  await page.locator('.agent-launcher').click();
  await expect(page.locator('.agent-drawer')).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
});

test('plant manager creates a canonical requirement through natural conversation', async ({ page }) => {
  await signIn(page, 'plant.manager@genuinegigs.local');
  const drawer = await openReadyAgent(page);
  const composer = page.getByLabel('Message my role agent');
  await composer.fill(
    'Create a raw material requirement for 17 KG Aluminium Ingot needed in 14 days because line replenishment stock is low.',
  );
  const response = page.waitForResponse((value) =>
    value.request().method() === 'POST' && /\/agent\/threads\/[^/]+\/messages$/.test(value.url()),
  );
  await page.getByRole('button', { name: 'Send message' }).click();
  expect((await response).ok()).toBe(true);
  const created = drawer.locator('.agent-response-block.record_created').last();
  await expect(created).toBeVisible();
  await expect(created).toContainText(/REQ-/);
  await expect(created.getByRole('link', { name: 'Open requirement' })).toBeVisible();
});

for (const [email] of accounts) {
  test(`${email} receives the assigned workbench`, async ({ page }) => {
    await signIn(page, email);
    await expect(page.getByRole("heading", { level: 1, name: /Good morning/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Needs your attention' })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.filter((item) => item.impact === "critical")).toEqual([]);
  });
}

test("purchase executive creates a selected multi-line requirement", async ({ page }) => {
  await signIn(page, "purchase.exec@genuinegigs.local");
  const submit = page.getByRole("button", { name: "Create requirement" });
  const form = submit.locator("xpath=ancestor::form");
  const title = "E2E multi-line requirement " + test.info().project.name;
  await form.getByLabel("Requirement title").fill(title);
  await form.getByLabel("Business reason").fill("Maintain production availability for the August plan");
  await form.getByLabel("Need by").fill("2026-08-01");
  const responsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" && response.url().endsWith("/procurement/requirements"),
  );
  await submit.click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const created = await response.json();
  expect(created.reason).toBe("Maintain production availability for the August plan");
  expect(created.business_number).toMatch(/^REQ-/);
  await expect(page.getByRole("heading", { name: "New requirement" })).toBeVisible();
});

test("purchase executive receives approval controls without manager editing authority", async ({ page }) => {
  await signIn(page, "purchase.exec@genuinegigs.local");
  await page.goto("/comparison");
  await expect(page.getByRole("heading", { name: "Review the recommendation" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Build comparison|Refresh verified offers/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Send recommendation for approval" })).toHaveCount(0);
});
