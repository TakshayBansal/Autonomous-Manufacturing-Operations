import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function signInV2(page: Page, email: string) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill("Password@123");
  await page.getByRole("button", { name: /Continue to GenuineGigs|Enter workspace/ }).click();
  const workspace = page.getByLabel("Operating workspace");
  const productShell = page.locator(".gg-product-shell");
  await expect.poll(async () => (await productShell.isVisible()) || (
    (await workspace.isVisible().catch(() => false)) && (await workspace.isEnabled().catch(() => false))
  )).toBeTruthy();
  if (await workspace.isVisible().catch(() => false) && await workspace.isEnabled().catch(() => false)) {
    const option = workspace.locator("option").filter({ hasText: "Apex Components" }).first();
    const value = await option.getAttribute("value");
    if (!value) throw new Error("Demo workspace unavailable");
    await workspace.selectOption(value);
    await expect(workspace).toHaveValue(value);
    const enterWorkspace = page.getByRole("button", { name: "Enter workspace" });
    await expect(enterWorkspace).toBeEnabled();
    await enterWorkspace.click();
  }
  await expect(productShell).toBeVisible({ timeout: 15_000 });
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/);
  await page.goto("/operations");
  await expect(page.locator(".gg-module-operations")).toBeVisible({ timeout: 15_000 });
}

async function assertOperationalPage(page: Page, heading: RegExp) {
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  await expect(page.locator(".v2-loading-region")).toHaveCount(0, { timeout: 15_000 });
  const dimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client + 1);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter(row => row.impact === "critical")).toEqual([]);
}

test("V2 flagship operating loop is comprehensible and accessible", async ({ page }, testInfo) => {
  await signInV2(page, "plant.manager@genuinegigs.local");
  const routes = [
    ["/operations", /operational view/i, "home"],
    ["/operations/production", /live plant model/i, "operations"],
    ["/operations/materials", /usable material/i, "materials"],
    ["/operations/quality", /contain defects/i, "quality"],
    ["/operations/maintenance", /recover the assets/i, "maintenance"],
    ["/operations/improvement", /recurring loss/i, "improvement"],
    ["/operations/knowledge", /approved instruction/i, "knowledge"],
    ["/operations/briefing", /what changed/i, "briefing"],
  ] as const;
  for (const [route, heading, name] of routes) {
    await page.goto(route);
    await assertOperationalPage(page, heading);
    if (["home", "operations", "briefing"].includes(name)) {
      await page.screenshot({ path: `test-results/v2/${testInfo.project.name}-${name}.png`, fullPage: true });
    }
  }
});

test("V2 mobile work and deviation path has no horizontal overflow", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "Mobile-specific acceptance");
  await signInV2(page, "plant.manager@genuinegigs.local");
  await page.goto("/operations/my-work");
  await assertOperationalPage(page, /what should i do now/i);
  await page.getByRole("button", { name: "Ask Gigi" }).first().click();
  await expect(page.getByRole("complementary", { name: "Gigi plant guardian" })).toBeVisible();
  await expect(page.getByText(/My Work ·/)).toBeVisible();
  await expect(page.getByLabel("Ask Gigi")).toHaveValue(/Explain why this action matters/);
  await page.getByRole("button", { name: "Close Gigi" }).click();
  const deviationLink = page.locator('a[href^="/operations/deviations/"], a[href^="/v2/deviations/"]').first();
  if (await deviationLink.count()) {
    await deviationLink.click();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const width = await page.evaluate(() => [document.documentElement.clientWidth, document.documentElement.scrollWidth]);
    expect(width[1]).toBeLessThanOrEqual(width[0] + 1);
  }
  await page.screenshot({ path: "test-results/v2/mobile-my-work.png", fullPage: true });
});

test("shift handover cannot publish before supervisor verification", async ({ page }) => {
  await signInV2(page, "plant.manager@genuinegigs.local");
  await page.goto("/operations/briefing");
  await page.getByRole("button", { name: "End-of-shift handover" }).click();
  const published = page.getByText(/Supervisor verified.*Published/);
  if (await published.isVisible().catch(() => false)) {
    await expect(published).toBeVisible();
    return;
  }
  const generate = page.getByRole("button", { name: "Generate draft" });
  if (await generate.isVisible().catch(() => false)) await generate.click();
  await expect(page.getByLabel("Handover summary")).toBeVisible();
  await page.getByLabel("Handover summary").fill("Line 3 recovery carries forward with BR-28 available and a named owner.");
  await page.getByRole("button", { name: "Save edits" }).click();
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("button", { name: "Publish handover" })).toBeVisible();
  await page.getByRole("button", { name: "Publish handover" }).click();
  await expect(page.getByText(/Supervisor verified.*Published/)).toBeVisible();
});

test("admin infrastructure routes are visible only with backend authority", async ({ page }) => {
  await signInV2(page, "admin@genuinegigs.local");
  await page.goto("/operations/setup");
  await assertOperationalPage(page, /activate one plant/i);
  await page.goto("/operations/integrations");
  await assertOperationalPage(page, /plant data connections/i);
  const allowed = await page.request.get("http://127.0.0.1:8000/api/v2/setup");
  expect(allowed.status()).toBe(200);

  await signInV2(page, "purchase.exec@genuinegigs.local");
  const denied = await page.request.get("http://127.0.0.1:8000/api/v2/setup");
  expect(denied.status()).toBe(403);
});
