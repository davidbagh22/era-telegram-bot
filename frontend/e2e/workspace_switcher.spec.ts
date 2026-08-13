import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const LEADER_TELEGRAM_ID = 900002;
const PARTICIPANT_TELEGRAM_ID = 900001;

// Regression coverage for the Personal <-> Admin/Leader workspace-mode
// switcher (App.tsx's `inWorkspace` state): before this existed, an admin
// or leader had no route at all to their own personal Mini App — they
// landed in Admin/Leader Mode and stayed there. "<- Личное" in
// AdminLayout/LeaderLayout and the "Управление ЭРА" card in ProfileScreen
// are the only ways in/out, so this exercises the full round trip through
// the real UI rather than just asserting the pieces exist in isolation.

test("admin can leave Admin Mode for their personal space and return", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(page.getByText("Управление")).toBeVisible();

  await page.getByRole("button", { name: "← Личное" }).click();

  // Personal Home, with the standard participant bottom navigation — not a
  // dead end or a blank screen.
  await expect(page.getByRole("button", { name: "Профиль" })).toBeVisible();
  await expect(page.getByText("Управление")).not.toBeVisible();

  await page.getByRole("button", { name: "Профиль" }).click();
  const workspaceCard = page.locator(".era-card", { hasText: "Управление ЭРА" });
  await expect(workspaceCard).toBeVisible();
  await expect(workspaceCard.getByText("Режим администратора")).toBeVisible();

  await workspaceCard.getByRole("button", { name: "Перейти" }).click();

  // Back in Admin Mode, landing on the same Overview it always has.
  await expect(page.getByText("Управление")).toBeVisible();
  await expect(page.getByRole("button", { name: "← Личное" })).toBeVisible();
});

test("leader can leave Leader Mode for their personal space and return", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${LEADER_TELEGRAM_ID}`);
  await expect(page.getByRole("heading", { name: "Панель лидера" })).toBeVisible();

  await page.getByRole("button", { name: "← Личное" }).click();
  await expect(page.getByRole("button", { name: "Профиль" })).toBeVisible();

  await page.getByRole("button", { name: "Профиль" }).click();
  const workspaceCard = page.locator(".era-card", { hasText: "Управление ЭРА" });
  await expect(workspaceCard).toBeVisible();
  await expect(workspaceCard.getByText("Режим лидера")).toBeVisible();

  await workspaceCard.getByRole("button", { name: "Перейти" }).click();
  await expect(page.getByRole("heading", { name: "Панель лидера" })).toBeVisible();
});

test("a plain participant's profile has no workspace switcher card", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль" }).click();

  // Its absence — not a hidden/disabled button — is what keeps a
  // participant off a workspace they don't have (see ProfileScreen.tsx's
  // onEnterWorkspace prop).
  await expect(page.locator(".era-card", { hasText: "Управление ЭРА" })).toHaveCount(0);
});
