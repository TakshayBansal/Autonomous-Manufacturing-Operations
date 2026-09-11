import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith("/app-context")) body = {
      user: { name: "Factory Manager", role: "admin", id: "u", tenant_id: "t", plant_id: "p" },
      workspace: { name: "Automotive contract fixture", id: "t" },
      plant: { id: "p", name: "Plant A" }, notification_count: 0, source_health: "unknown",
      modules: ["procurement", "scm", "operations", "platform"].map(key => ({ key, label: key, enabled: true, default_route: `/${key}` })),
    };
    if (path.endsWith("/home")) body = {
      attention: [], module_summaries: {}, operational_cases: [], decision_count: 0, recovery_count: 0,
      exposure: [{ metric: "production_units_at_risk", delta: 440, unit: "EA" }, { metric: "affected_hours", delta: 12, unit: "hours" }],
      verified_value: [], generated_at: "2026-09-07T10:00:00Z",
    };
    await route.fulfill({ json: body });
  });
});

test("command center keeps unlike exposures separate and central administration opens", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/home");
  await expect(page.getByRole("heading", { name: "Protect production. Coordinate recovery." })).toBeVisible();
  await expect(page.getByText("440 EA", { exact: true })).toBeVisible();
  await expect(page.getByText("12 hours", { exact: true })).toBeVisible();
  await expect(page.getByText("452", { exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "Data & Integrations", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "One entry point for factory data." })).toBeVisible();
  expect(errors).toEqual([]);
});

test("failed companion requests never report healthy factory state", async ({ page }) => {
  await page.route("**/api/v1/gigi/insights", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.goto("/home");
  await page.getByRole("button", { name: /Open Gigi companion/ }).click();
  await expect(page.getByText("Operational context unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("Stable for now", { exact: true })).toHaveCount(0);
});

test("decision loading failures remain actionable", async ({ page }) => {
  await page.route("**/api/v1/decision-inbox", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.goto("/decisions");
  await expect(page.getByText("Decision queue unavailable", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toBeVisible();
  await expect(page.getByText("No decisions returned for your scope")).toHaveCount(0);
});
