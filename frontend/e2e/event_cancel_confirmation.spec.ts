import { expect, test } from "@playwright/test";

// PR 37 (UI Design System): "Планы изменились" (cancel registration) used
// to fire the cancellation on a single tap — no destructive action in the
// app had a confirmation step. It now opens a BottomSheet first. This
// registers-then-cancels through the real stack, independently of
// participant.spec.ts (which only registers and stops), so the seeded
// participant ends this spec back in the "not registered" state rather
// than leaving a side effect another spec might trip over.

const PARTICIPANT_TELEGRAM_ID = 900001;

test("cancelling a registration goes through a confirm sheet, not an immediate tap", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Активность" }).click();
  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();

  await page.getByRole("button", { name: "Зарегистрироваться" }).click();
  const cancelTrigger = page.getByRole("button", { name: "Планы изменились" });
  await expect(cancelTrigger).toBeVisible();

  await cancelTrigger.click();
  await expect(page.getByText("Отменить регистрацию?")).toBeVisible();

  // Backing out of the sheet must not cancel the registration.
  await page.getByRole("button", { name: "Не отменять" }).click();
  await expect(page.getByText("Отменить регистрацию?")).not.toBeVisible();
  await expect(cancelTrigger).toBeVisible();

  await cancelTrigger.click();
  await page.getByRole("button", { name: "Отменить регистрацию" }).click();

  // Real cancellation through the full stack — the button reverting to
  // "Зарегистрироваться" only happens once the refetched event's
  // registration_status is no longer an active one.
  await expect(page.getByRole("button", { name: "Зарегистрироваться" })).toBeVisible();
  await expect(page.getByText("Регистрация отменена")).toBeVisible();
});
