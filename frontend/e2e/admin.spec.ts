import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

test("admin logs in and approves the seeded pending applicant", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);

  // AdminLayout's header, not a screen heading — confirms the admin branch
  // of App.tsx rendered (is_admin === true), not the plain participant one.
  await expect(page.getByText("ЭРА / ADMIN")).toBeVisible();

  await page.getByRole("button", { name: "Заявки" }).click();

  const applicantCard = page.getByText("E2E Pending Applicant");
  await expect(applicantCard).toBeVisible();

  await page.getByRole("button", { name: "Одобрить" }).click();

  // A real approval through application_review_service → DB, not a UI-only
  // removal — verified by the applicant disappearing after the screen
  // refetches the (now-empty) pending queue from the API.
  await expect(page.getByText("E2E Pending Applicant")).not.toBeVisible();
});
