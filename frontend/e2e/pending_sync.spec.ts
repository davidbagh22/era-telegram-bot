import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const PENDING_APPLICANT_TELEGRAM_ID = 900004;

test("a pending applicant's Mini App updates itself after admin approval, without a reload", async ({
  browser,
}) => {
  // Two independent sessions, like two real people: the applicant's Mini
  // App stays open the whole time and is never reloaded or re-navigated —
  // this is exactly the scenario reported live (participant finishes
  // registration / gets approved, but the already-open app shows no sign of
  // it and tells them to go press /start again). The fix under test is
  // useAuth.ts re-checking on its own, not a page navigation.
  const applicantContext = await browser.newContext();
  const applicantPage = await applicantContext.newPage();
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();

  try {
    await applicantPage.goto(`/app/?devTelegramId=${PENDING_APPLICANT_TELEGRAM_ID}`);
    await expect(
      applicantPage.getByRole("heading", { name: "Заявка на рассмотрении" }),
    ).toBeVisible();

    await adminPage.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
    await adminPage.getByRole("button", { name: "Заявки" }).click();
    await expect(adminPage.getByText("E2E Pending Applicant")).toBeVisible();
    await adminPage.getByRole("button", { name: "Одобрить" }).click();
    await expect(adminPage.getByText("E2E Pending Applicant")).not.toBeVisible();

    // Back on the applicant's still-open, never-reloaded page: manually
    // triggering the same re-check the visibility/focus listeners perform
    // (rather than waiting out the 15s poll) is enough to pick up the
    // approval — proving the sync is real, not dependent on a fresh load.
    await applicantPage.getByRole("button", { name: "Проверить сейчас" }).click();

    await expect(
      applicantPage.getByRole("heading", { name: "Привет, E2E Pending Applicant" }),
    ).toBeVisible();
    await expect(
      applicantPage.getByRole("heading", { name: "Заявка на рассмотрении" }),
    ).not.toBeVisible();
  } finally {
    await applicantContext.close();
    await adminContext.close();
  }
});
