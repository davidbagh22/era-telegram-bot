import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const LEADER_TELEGRAM_ID = 900002;
const PARTICIPANT_TELEGRAM_ID = 900001;

function profileTab(page: import("@playwright/test").Page) {
  return page
    .getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true });
}

async function openProfile(page: import("@playwright/test").Page) {
  await expect(profileTab(page)).toBeVisible();
  await profileTab(page).click();
}

// Regression coverage for the Personal <-> Admin/Leader workspace-mode
// switcher: elevated roles must start in the same personal ERA product as
// everyone else, explicitly enter management, leave it, and enter again.

test("admin starts personal, enters Admin Mode, leaves it, and returns", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);

  // Elevated permissions must not replace the person's own Mini App on load.
  await expect(profileTab(page)).toBeVisible();
  await expect(page.getByText("Управление", { exact: true })).toHaveCount(0);

  await openProfile(page);
  const workspaceButton = page.getByRole("button", {
    name: /Управление ЭРА.*Открыть режим администратора/,
  });
  await expect(workspaceButton).toBeVisible();
  await workspaceButton.click();

  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "← Личное" })).toBeVisible();

  await page.getByRole("button", { name: "← Личное" }).click();
  await expect(profileTab(page)).toBeVisible();
  await expect(page.getByText("Управление", { exact: true })).toHaveCount(0);

  await openProfile(page);
  await page.getByRole("button", { name: /Управление ЭРА.*Открыть режим администратора/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
});

test("leader starts personal, enters Leader Mode, leaves it, and returns", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${LEADER_TELEGRAM_ID}`);

  await expect(profileTab(page)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Пространство лидера" })).toHaveCount(0);

  await openProfile(page);
  const workspaceButton = page.getByRole("button", {
    name: /Управление ЭРА.*Открыть пространство лидера/,
  });
  await expect(workspaceButton).toBeVisible();
  await workspaceButton.click();
  await expect(page.getByRole("heading", { name: "Пространство лидера" })).toBeVisible();

  await page.getByRole("button", { name: "← Личное" }).click();
  await expect(profileTab(page)).toBeVisible();

  await openProfile(page);
  await page.getByRole("button", { name: /Управление ЭРА.*Открыть пространство лидера/ }).click();
  await expect(page.getByRole("heading", { name: "Пространство лидера" })).toBeVisible();
});

test("a plain participant's profile has no workspace switcher action", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await openProfile(page);

  await expect(page.getByRole("button", { name: /Управление ЭРА/ })).toHaveCount(0);
});
