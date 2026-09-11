import { expect, test, type Page } from '@playwright/test';

const screenshotDir = 'test-results/client-demo';

async function signIn(page: Page, email: string) {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await page.goto('/login');
  await page.getByLabel('Work email').fill(email);
  await page.getByLabel('Password').fill('Password@123');
  await page.getByRole('button', { name: 'Continue to GenuineGigs' }).click();
  const workspace = page.getByLabel('Operating workspace');
  const productShell = page.locator('.gg-product-shell');
  await expect.poll(async () => (await workspace.isVisible()) || (await productShell.isVisible())).toBeTruthy();
  if (await workspace.isVisible().catch(() => false)) {
    const demoWorkspace = workspace.locator('option').filter({ hasText: 'Apex Components' }).first();
    await expect(demoWorkspace).toHaveCount(1);
    const value = await demoWorkspace.getAttribute('value');
    if (!value) throw new Error('Demo workspace unavailable');
    await workspace.selectOption(value);
    await expect(workspace).toHaveValue(value);
    const enterWorkspace = page.getByRole('button', { name: 'Enter workspace' });
    await expect(enterWorkspace).toBeEnabled();
    await enterWorkspace.click();
  }
  await expect(productShell).toBeVisible({ timeout: 15_000 });
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
  await page.goto('/procurement');
}

async function capture(page: Page, name: string) {
  if (await page.locator('.agent-drawer').isVisible().catch(() => false)) {
    await expect(page.locator('.agent-drawer-loading')).toBeHidden({ timeout: 15_000 });
    await expect(page.getByLabel('Message my role agent')).toBeEnabled({ timeout: 15_000 });
  }
  await page.screenshot({ path: `${screenshotDir}/${name}.png`, fullPage: true });
}

test('capture the minimum client-demo evidence set', async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  test.skip(testInfo.project.name !== 'desktop', 'One canonical desktop evidence run');

  await page.setViewportSize({ width: 1440, height: 900 });
  await signIn(page, 'plant.manager@genuinegigs.local');
  await capture(page, '01-my-work-plant-manager');

  for (const [name, width, height] of [
    ['10-my-work-1440x900', 1440, 900],
    ['11-my-work-1280x800', 1280, 800],
    ['12-my-work-1024x768', 1024, 768],
    ['13-my-work-768x1024', 768, 1024],
    ['14-my-work-390x844', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    await capture(page, name);
  }

  const drawer = page.locator('.agent-drawer');
  await expect(async () => {
    if (!(await drawer.isVisible().catch(() => false))) {
      await page.getByRole('button', { name: 'Open role agent' }).click();
    }
    await expect(drawer).toBeVisible({ timeout: 2_000 });
    await expect(page.locator('.agent-drawer-loading')).toBeHidden({ timeout: 2_000 });
    await expect(page.getByLabel('Message my role agent')).toBeEnabled({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  await capture(page, '03-assistant-successful-requirement');

  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, '09-mobile-assistant-drawer');

  await page.setViewportSize({ width: 1280, height: 900 });
  await signIn(page, 'purchase.exec@genuinegigs.local');
  await capture(page, '02-my-work-purchase-executive');
  await page.goto('/procurement');
  await expect(page.getByRole('heading', { name: 'Create new requirement' })).toBeVisible();
  await capture(page, '15-material-requirements');
  await page.goto('/procurement/rfqs');
  await expect(page.getByRole('heading', { name: /RFQ/i }).first()).toBeVisible();
  await capture(page, '04-assistant-rfq-result');
  await capture(page, '08-rfq-review-and-send');

  await signIn(page, 'purchase.manager@genuinegigs.local');
  await page.goto('/procurement/quotations');
  await capture(page, '05-quotation-extraction-review');
  await page.goto('/procurement/comparison');
  await capture(page, '06-comparison-recommendation');
  await page.goto('/procurement/approvals');
  await capture(page, '07-approval-brief');

  await signIn(page, 'admin@genuinegigs.local');
  await page.goto('/integrations');
  await expect(page.getByRole('heading', { name: 'Inspect before anything changes' })).toBeVisible();
  await capture(page, '16-integration-centre');
});
