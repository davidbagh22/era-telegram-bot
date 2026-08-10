import { expect, test } from "@playwright/test";

const LEADER_TELEGRAM_ID = 900002;
const ADMIN_TELEGRAM_ID = 900003;
// Seeded directly by scripts/e2e_seed.py as a pending submission on "E2E
// завершённое мероприятие" (responsible_id = the E2E leader) — a real
// bot-side proof submission needs a live Telegram client, out of reach
// for Playwright, so this stands in for one (same gap task_submit_deep_link
// has, with no existing E2E coverage of that FSM either).
const ACTIVITY_TITLE = "E2E активность";
const SUBMITTER_NAME = "E2E Activity Submitter";

test("leader pre-approves an activity submission, then the admin does the final review", async ({
  browser,
}) => {
  const leaderContext = await browser.newContext();
  const leaderPage = await leaderContext.newPage();
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();

  try {
    await leaderPage.goto(`/app/?devTelegramId=${LEADER_TELEGRAM_ID}`);
    await expect(leaderPage.getByRole("heading", { name: "Панель лидера" })).toBeVisible();
    await leaderPage.getByRole("button", { name: "Активности" }).click();

    const leaderCard = leaderPage.locator(".era-card", { hasText: ACTIVITY_TITLE });
    await expect(leaderCard).toBeVisible();
    await expect(leaderCard.getByText(SUBMITTER_NAME)).toBeVisible();
    await leaderCard.getByRole("button", { name: "✅ Принять" }).click();

    // A real decision through the full stack (API -> event_activity_service
    // -> DB), verified by the submission leaving the leader's own pending
    // queue after the screen refetches it.
    await expect(leaderPage.locator(".era-card", { hasText: ACTIVITY_TITLE })).toHaveCount(0);

    await adminPage.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
    await expect(adminPage.getByText("ЭРА / ADMIN")).toBeVisible();
    await adminPage.getByRole("button", { name: "Мероприятия" }).click();
    await adminPage.getByRole("button", { name: "Активности" }).click();

    const adminCard = adminPage.locator(".era-card", { hasText: ACTIVITY_TITLE });
    await expect(adminCard).toBeVisible();
    await expect(adminCard.getByText("проверено лидером")).toBeVisible();
    await adminCard.getByRole("button", { name: "✅ Принять и начислить" }).click();

    // A real final approval through the full stack — points are awarded
    // exactly once (see event_activity_service.admin_decide's dedup
    // guard) — verified by the submission leaving the review queue.
    await expect(adminPage.locator(".era-card", { hasText: ACTIVITY_TITLE })).toHaveCount(0);
  } finally {
    await leaderContext.close();
    await adminContext.close();
  }
});
