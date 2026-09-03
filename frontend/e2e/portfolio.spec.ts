import { expect, test } from "@playwright/test";

// Closes part of docs/FINAL_PRODUCTION_ACCEPTANCE.md item #266
// ("Portfolio upload/view/delete flow has no E2E coverage"). Upload and
// delete genuinely can't be driven by Playwright — both are Bot-only FSM
// flows that need a live Telegram client (see scripts/e2e_seed.py's own
// comment on the same gap for event-activity proof submission). *View*
// has no such excuse: it's a plain Mini App screen reading real DB state
// through the real API, so this proves that half of the flow instead of
// leaving it silently uncovered next to the two halves that are.
const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant's earned badge appears in their portfolio", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  await page.getByRole("button", { name: "Профиль", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Мой путь" })).toBeVisible();

  // The redesigned Profile keeps achievements as a first-class cell and
  // opens them on their own screen instead of rendering the whole portfolio
  // in one long page. Verify both the navigation and the real awarded badge.
  await page.getByRole("button", { name: /Достижения/ }).click();
  await expect(page.getByRole("heading", { name: "Достижения" })).toBeVisible();
  await expect(page.getByText("E2E Тестовый значок")).toBeVisible();
});
