import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

test("admin logs in and approves the seeded pending applicant", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);

  // AdminLayout's header, not a screen heading — confirms the admin branch
  // of App.tsx rendered (is_admin === true, and workspace mode, not the
  // plain participant one).
  await expect(page.getByText("Управление")).toBeVisible();

  // Заявки now lives under the Люди group — see AdminScreen.tsx's 2026-08
  // regrouping (5 top-level groups instead of one flat 12-tab row).
  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: "Заявки" }).click();

  const applicantCard = page.getByText("E2E Pending Applicant");
  await expect(applicantCard).toBeVisible();

  // Scoped to this applicant's own card, not a bare global lookup: the
  // queue can (and, once pending_sync.spec.ts's own fixture is also
  // pending, does) hold more than one applicant at once, each with an
  // identical "Одобрить" button.
  await page
    .locator(".era-card", { hasText: "E2E Pending Applicant" })
    .getByRole("button", { name: "Одобрить" })
    .click();

  // A real approval through application_review_service → DB, not a UI-only
  // removal — verified by the applicant disappearing after the screen
  // refetches the (now-empty) pending queue from the API.
  await expect(page.getByText("E2E Pending Applicant")).not.toBeVisible();
});
