import { expect, test, type Page } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900002;

async function openVector(page: Page) {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: /Как ты изменился за последний месяц/ }).click();
  const consent = page.getByRole("button", { name: "Понятно, продолжить" });
  if (await consent.isVisible().catch(() => false)) await consent.click();
  await expect(page.getByRole("heading", { name: "Мой вектор" })).toBeVisible();
}

test("monthly check-in resumes from server answers and produces one focus", async ({ page }) => {
  await openVector(page);
  await page.getByRole("button", { name: /Посмотрим, что изменилось|Посмотреть результат месяца/ }).click();

  await expect(page.getByText("За последние две недели у меня хватало энергии на обычные дела.")).toBeVisible();
  await page.getByRole("button", { name: "Скорее да" }).click();
  await page.getByRole("button", { name: "Скорее да" }).click();

  await page.getByRole("button", { name: "Продолжить позже" }).click();
  await expect(page.getByRole("heading", { name: "Мой вектор" })).toBeVisible();
  await page.getByRole("button", { name: /Посмотрим, что изменилось|Посмотреть результат месяца/ }).click();

  // The first two core answers were saved server-side, so the resumed flow
  // starts from the third core question rather than from energy again.
  await expect(page.getByText(/В важных для меня ситуациях я чаще принимал решения/)).toBeVisible();

  // First check-in contains five comparable state questions plus one themed
  // reflection question. Two were already answered above.
  for (let index = 0; index < 4; index += 1) {
    await page.getByRole("button", { name: "Скорее да" }).click();
  }

  await expect(page.getByRole("heading", { name: "Контекст месяца" })).toBeVisible();
  await page.getByRole("button", { name: "учёба" }).click();
  await page.getByRole("button", { name: "уверенность" }).click();
  await page.getByRole("button", { name: "Получить мой результат" }).click();

  await expect(page.getByText("ТВОЙ ФОКУС МЕСЯЦА")).toBeVisible();
  await expect(page.getByRole("button", { name: "Почему?" })).toBeVisible();
  await expect(page.getByText("Администратор эту заметку не видит.")).toBeVisible();
});
