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

  // scripts/e2e_seed.py awards this badge to the E2E participant directly
  // through the DB (the same effect an admin's real "award badge" action
  // has) — seeing it render here proves the Profile screen's portfolio
  // section is reading real, awarded state, not a fixture the UI itself
  // fabricated.
  await expect(page.getByText("Достижения")).toBeVisible();
  await expect(page.getByText("E2E Тестовый значок")).toBeVisible();
});
