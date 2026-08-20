import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant gets light ERA UI, opens event details, and registers", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  // The Vector-first Home card is the stable landmark for every approved
  // participant after the growth-system redesign.
  await expect(page.getByText("МОЙ ВЕКТОР", { exact: true })).toBeVisible();
  const bodyBackground = await page.locator("body").evaluate((node) => getComputedStyle(node).backgroundColor);
  // The redesign is light-first by design (tokens.css §0/§2) -- the old
  // near-black surface must never come back as the default body color.
  expect(bodyBackground).not.toBe("rgb(17, 17, 24)");

  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "События" }).click();
  await expect(page.getByRole("heading", { name: "События" })).toBeVisible();

  const eventCard = page.getByText("E2E тестовое мероприятие");
  await expect(eventCard).toBeVisible();
  await page.getByRole("button", { name: "Открыть событие" }).first().click();

  await expect(page.getByRole("heading", { name: "E2E тестовое мероприятие" })).toBeVisible();
  await page.getByRole("button", { name: "Участвовать" }).click();

  await expect(page.getByRole("heading", { name: "Место за вами" })).toBeVisible();
  await expect(page.getByText("✓ Вы участвуете").first()).toBeVisible();
  await page.getByRole("button", { name: "Готово" }).click();
  await expect(page.getByRole("button", { name: "Отказаться" })).toBeVisible();
});
