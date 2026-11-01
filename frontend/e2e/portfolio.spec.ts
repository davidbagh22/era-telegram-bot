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

  const profileResponse = page.waitForResponse(
    (response) => /\/api\/v1\/profile(?:\?|$)/.test(response.url()) && response.status() === 200,
  );
  await page.getByRole("button", { name: "Профиль", exact: true }).click();
  const profile = (await (await profileResponse).json()) as { city: string; growth: { label: string } };
  const identity = page.getByTestId("profile-identity");
  await expect(identity).toBeVisible();
  if (profile.growth.label) {
    // Removing the old "Мой путь" card must also remove its residual stage label.
    await expect(identity).not.toContainText(profile.growth.label);
  }
  if (profile.city) {
    await expect(page.getByTestId("profile-location")).toHaveText(profile.city);
  } else {
    await expect(page.getByTestId("profile-location")).toHaveCount(0);
  }
  await expect(page.getByRole("heading", { name: "Мой вклад и опыт" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Мой путь", exact: true })).toHaveCount(0);
  await expect(page.getByText("этап пути", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "История участия" })).toBeVisible();

  // The redesigned Profile keeps achievements as a first-class cell and
  // opens them on their own screen instead of rendering the whole portfolio
  // in one long page. Verify both the navigation and the real awarded badge.
  await page.getByRole("button", { name: /Достижения/ }).click();
  await expect(page.getByRole("heading", { name: "Достижения" })).toBeVisible();
  await expect(page.getByText("E2E Тестовый значок")).toBeVisible();
});

test("profile dashboard cells fit a narrow mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Мой вклад и опыт" })).toBeVisible();

  const cells = page.locator("section").filter({ has: page.getByRole("heading", { name: "Мой вклад и опыт" }) }).locator("button");
  await expect(cells).toHaveCount(6);
  for (const cell of await cells.all()) {
    await expect(cell).toBeVisible();
    const fits = await cell.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const label = element.querySelector("strong");
      return rect.left >= 0 && rect.right <= window.innerWidth + 1
        && element.scrollWidth <= element.clientWidth + 1
        && (!label || label.scrollWidth <= label.clientWidth + 1);
    });
    expect(fits).toBe(true);
  }

  await page.getByRole("button", { name: /Волонтёрство/ }).click();
  await expect(page.getByRole("heading", { name: "Волонтёрство" })).toBeVisible();
});
