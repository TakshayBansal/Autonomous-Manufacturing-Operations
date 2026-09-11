import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("admin@genuinegigs.local");
  await page.getByLabel("Password").fill("Password@123");
  await page.getByRole("button", { name: /Continue to GenuineGigs/ }).click();
  const workspace = page.getByLabel("Operating workspace");
  if (await workspace.isVisible().catch(() => false)) {
    await workspace.selectOption({ index: 1 });
    await page.getByRole("button", { name: "Enter workspace" }).click();
  }
  await expect(page).toHaveURL(/\/home$/);
}

test("one session moves through the unified product modules", async ({ page }) => {
  await signIn(page);
  await expect(page.locator(".gg-module-home")).toBeVisible();
  await expect(page.getByRole("link", { name: "Procurement" })).toBeVisible();
  await expect(page.getByRole("link", { name: "SCM" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Operations" })).toBeVisible();

  await page.getByRole("link", { name: "Procurement" }).first().click();
  await expect(page).toHaveURL(/\/procurement$/);
  await expect(page.locator(".gg-module-procurement")).toBeVisible();

  await page.getByRole("link", { name: "SCM" }).first().click();
  await expect(page).toHaveURL(/\/scm$/);
  await expect(page.locator(".gg-module-scm")).toBeVisible();

  await page.getByRole("link", { name: "Operations" }).first().click();
  await expect(page).toHaveURL(/\/operations$/);
  await expect(page.locator(".gg-module-operations")).toBeVisible();
});

test("legacy module URLs land on canonical product routes", async ({ page }) => {
  await signIn(page);
  await page.goto("/v2/home");
  await expect(page).toHaveURL(/\/operations$/);
  await page.goto("/control-centre");
  await expect(page).toHaveURL(/\/procurement$/);
});
