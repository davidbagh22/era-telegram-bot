import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const PENDING_SYNC_APPLICANT_TELEGRAM_ID = 900005;

test("a pending applicant's Mini App updates itself after admin approval, without a reload", async ({
  browser,
  request,
}) => {
  // The applicant's Mini App page stays open the whole time and is never
  // reloaded or re-navigated — this is exactly the scenario reported live
  // (participant finishes registration / gets approved, but the
  // already-open app shows no sign of it and tells them to go press
  // /start again). The fix under test is useAuth.ts re-checking on its
  // own, not a page navigation.
  const applicantContext = await browser.newContext();
  const applicantPage = await applicantContext.newPage();

  try {
    await applicantPage.goto(`/app/?devTelegramId=${PENDING_SYNC_APPLICANT_TELEGRAM_ID}`);
    await expect(
      applicantPage.getByRole("heading", { name: "Заявка на рассмотрении" }),
    ).toBeVisible();

    // Approve through the real API directly (not the Admin UI's
    // Applications screen) — that screen shares its single global
    // "Одобрить" button across every pending row, and admin.spec.ts
    // already exercises that exact click against its own dedicated
    // applicant. Driving the approval through the API here keeps this
    // test fully independent of admin.spec.ts and of test execution
    // order, while still being a real approval through the same
    // application_review_service the UI button calls.
    const authResponse = await request.post("/api/v1/miniapp/auth", {
      data: { initData: "", devTelegramId: ADMIN_TELEGRAM_ID },
    });
    expect(authResponse.ok()).toBeTruthy();
    const { token } = await authResponse.json();

    const applicationsResponse = await request.get("/api/v1/admin/applications", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(applicationsResponse.ok()).toBeTruthy();
    const applications = (await applicationsResponse.json()) as Array<{
      id: number;
      telegram_id: number;
    }>;
    const applicant = applications.find(
      (app) => app.telegram_id === PENDING_SYNC_APPLICANT_TELEGRAM_ID,
    );
    expect(applicant, "seeded pending_sync applicant should still be in the queue").toBeTruthy();

    const approveResponse = await request.post(
      `/api/v1/admin/applications/${applicant!.id}/approve`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(approveResponse.ok()).toBeTruthy();

    // Back on the applicant's still-open, never-reloaded page: manually
    // triggering the same re-check the visibility/focus listeners perform
    // (rather than waiting out the 15s poll) is enough to pick up the
    // approval — proving the sync is real, not dependent on a fresh load.
    await applicantPage.getByRole("button", { name: "Проверить сейчас" }).click();

    // The approved user now lands in the redesigned dark Home. ERA SCORE
    // is the stable product landmark; the old "держим темп" heading was
    // removed by the final design system and must not be used as a test hook.
    await expect(applicantPage.getByText("ERA SCORE")).toBeVisible();
    await expect(applicantPage.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(
      applicantPage.getByRole("heading", { name: "Заявка на рассмотрении" }),
    ).not.toBeVisible();
  } finally {
    await applicantContext.close();
  }
});
