import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

test("admin creates an office and assigns the seeded participant to it", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(page.getByText("ЭРА / ADMIN")).toBeVisible();

  await page.getByRole("button", { name: "Должности" }).click();

  const officeTitle = `E2E Office ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(officeTitle);
  await page.getByRole("button", { name: "Добавить должность" }).click();

  // A real create through the full stack, verified by the office
  // appearing in the list after the screen refetches it from the API.
  await expect(page.getByText(officeTitle)).toBeVisible();

  // Scoped to this office's own card, not a bare global lookup: the app
  // seeds a full set of reference-data offices on every boot
  // (app/services/seed_service.py), so every one of them has an identical
  // "Назначить человека" button.
  const officeCard = page.locator(".era-card", { hasText: officeTitle });
  await officeCard.getByRole("button", { name: "Назначить человека" }).click();
  await officeCard.getByPlaceholder("Имя, username или Telegram ID").fill("E2E Participant");
  await officeCard.getByRole("button", { name: "Найти" }).click();
  await officeCard.getByRole("button", { name: "E2E Participant" }).click();

  // A real assignment through the full stack, verified by the participant's
  // name appearing in the office's own "Сейчас:" line after the refetch.
  await expect(officeCard.getByText(/Сейчас:.*E2E Participant/)).toBeVisible();
});
