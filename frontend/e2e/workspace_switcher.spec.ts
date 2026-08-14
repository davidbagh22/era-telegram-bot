import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const LEADER_TELEGRAM_ID = 900002;
const PARTICIPANT_TELEGRAM_ID = 900001;

// Regression coverage for the Personal <-> Admin/Leader workspace-mode
// switcher (App.tsx's `inWorkspace` state): admins/leaders must be able to
// leave the management workspace and return through the Profile ActionCell.

test("admin can leave Admin Mode for their personal space and return", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(page.getByText("Управление")).toBeVisible();

  await page.getByRole("button", { name: "← Личное" }).click();

  // Personal Home, with the standard participant bottom navigation — not a
  // dead end or a blank screen.
  await expect(page.getByRole("button", { name: "Профиль" })).toBeVisible();
  await expect(page.getByText("Управление")).not.toBeVisible();

  await page.getByRole("button", { name: "Профиль" }).click();
  const workspaceButton = page.getByRole("button", {
    name: /Управление ЭРА.*Открыть режим администратора/,
  });
  await expect(workspaceButton).toBeVisible();
  await workspaceButton.click();

  // Back in Admin Mode, landing on the same Overview it always has.
  await expect(page.getByText("Управление")).toBeVisible();
  await expect(page.getByRole("button", { name: "← Личное" })).toBeVisible();
});

test("leader can leave Leader Mode for their personal space and return", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${LEADER_TELEGRAM_ID}`);
  await expect(page.getByRole("heading", { name: "Пространство лидера" })).toBeVisible();

  await page.getByRole("button", { name: "← Личное" }).click();
  await expect(page.getByRole("button", { name: "Профиль" })).toBeVisible();

  await page.getByRole("button", { name: "Профиль" }).click();
  const workspaceButton = page.getByRole("button", {
    name: /Управление ЭРА.*Открыть пространство лидера/,
  });
  await expect(workspaceButton).toBeVisible();
  await workspaceButton.click();
  await expect(page.getByRole("heading", { name: "Пространство лидера" })).toBeVisible();
});

test("a plain participant's profile has no workspace switcher action", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль" }).click();

  // Its absence — not a hidden/disabled action — is what keeps a participant
  // off a workspace they don't have (see ProfileScreen.tsx onEnterWorkspace).
  await expect(page.getByRole("button", { name: /Управление ЭРА/ })).toHaveCount(0);
});
