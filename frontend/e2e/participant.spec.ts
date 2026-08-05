import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant logs in, sees Home, and registers for the seeded event", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  await expect(page.getByRole("heading", { name: "Привет, E2E Participant" })).toBeVisible();

  await page.getByRole("button", { name: "Активность" }).click();
  await expect(page.getByRole("heading", { name: "Активность" })).toBeVisible();

  const eventCard = page.getByText("E2E тестовое мероприятие");
  await expect(eventCard).toBeVisible();

  await page.getByRole("button", { name: "Зарегистрироваться" }).click();

  // A real registration through the full stack (API → event_service →
  // DB), not a UI-only toggle — verified by the button switching to the
  // cancel-registration label, which only renders when the freshly
  // refetched event's registration_status is an active one.
  await expect(page.getByRole("button", { name: "Планы изменились" })).toBeVisible();
});
