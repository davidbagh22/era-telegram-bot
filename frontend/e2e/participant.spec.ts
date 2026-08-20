import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant gets light ERA UI, opens event details, and registers", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  // The Vector-first Home card is the stable landmark for every approved
  // participant after the growth-system redesign.
  await expect(page.getByText("МОЙ ВЕКТОР", { exact: true })).toBeVisible();
  const bodyBackground = await page.locator("body").evaluate((node) => getComputedStyle(node).backgroundColor);
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

test("project constructor teaches each step, has no AI writer and lets the author delete a draft", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/projects`);
  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();

  const idea = `E2E черновик ${Date.now()}`;
  await page.getByPlaceholder("Мы делаем [что] для [кого], чтобы [зачем]").fill(idea);
  await page.getByRole("button", { name: "Начать конструктор →" }).click();

  await expect(page.getByText("Теория шага", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "В чём идея?" })).toBeVisible();
  await expect(page.getByText("Что написать", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Подробнее: вопросы и ошибки →" })).toBeVisible();

  await expect(page.getByText("AI-подсказка", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Помоги сформулировать" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Сделай короче" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Улучши мой вариант" })).toHaveCount(0);

  await page.getByRole("button", { name: "Удалить черновик" }).click();
  await expect(page.getByRole("heading", { name: "Удалить черновик?" })).toBeVisible();
  await page.getByRole("button", { name: "Удалить черновик" }).last().click();

  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
  await expect(page.getByText(idea, { exact: true })).toHaveCount(0);
});
