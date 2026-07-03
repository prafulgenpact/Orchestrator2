import { expect, test } from "@playwright/test";

// Template: one spec per user-visible flow, named after the acceptance
// criterion it proves. Grow task by task — same contract as tests/e2e/.
test("app loads and shows its main heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading").first()).toBeVisible();
});

// test("user can complete the primary flow", async ({ page }) => {
//   await page.goto("/");
//   await page.getByRole("button", { name: "New item" }).click();
//   await page.getByLabel("Name").fill("First item");
//   await page.getByRole("button", { name: "Save" }).click();
//   await expect(page.getByText("First item")).toBeVisible();
// });
