import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant gets AURA orbit UI, opens event details, and registers", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
  const bodyBackground = await page.locator("body").evaluate((node) => getComputedStyle(node).backgroundColor);
  // AURA base #19091a
  expect(bodyBackground).toBe("rgb(25, 9, 26)");

  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Афиша" }).click();
  await expect(page.getByRole("heading", { name: "Афиша", exact: true })).toBeVisible();

  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();
  await page.getByRole("button", { name: /E2E тестовое мероприятие/ }).first().click();

  await expect(page.getByRole("heading", { name: "E2E тестовое мероприятие" })).toBeVisible();
  await page.getByRole("button", { name: "Участвовать" }).click();

  await expect(page.getByRole("heading", { name: "Место за вами" })).toBeVisible();
  await expect(page.getByText("✓ Вы участвуете").first()).toBeVisible();
  await page.getByRole("button", { name: "Готово" }).click();
  await expect(page.getByRole("button", { name: "Отказаться" })).toBeVisible();
});

test("orbit nodes open people, ideas, and teams catalogs", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();

  await page.getByRole("navigation", { name: "Твоя орбита" }).getByRole("button", { name: /Люди/ }).click();
  await expect(page.getByRole("heading", { name: "Люди", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/#\/people/);

  await page.getByRole("button", { name: "← Орбита" }).click();
  await page.getByRole("navigation", { name: "Твоя орбита" }).getByRole("button", { name: /Идеи/ }).click();
  await expect(page.getByRole("heading", { name: "Идеи", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/#\/ideas/);

  await page.getByRole("button", { name: "← Орбита" }).click();
  await page.getByRole("navigation", { name: "Твоя орбита" }).getByRole("button", { name: /Команды/ }).click();
  await expect(page.getByRole("heading", { name: "Команды", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/#\/teams/);
});

test("the home board and group shortcuts open the intended event lists", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  const board = page.getByRole("region", { name: "Ближайшее" });
  await expect(board.getByText("E2E тестовое мероприятие")).toBeVisible();
  await board.getByRole("button", { name: "Афиша →" }).click();
  await expect(page.getByRole("heading", { name: "Афиша", exact: true })).toBeVisible();

  const personalEvents = page.waitForRequest((request) => new URL(request.url()).searchParams.get("scope") === "mine");
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}&tgWebAppStartParam=events_mine`);
  await personalEvents;
  await expect(page.getByRole("heading", { name: "Мои мероприятия", exact: true })).toBeVisible();
});

test("project constructor teaches each step, has no AI writer and lets the author delete a draft", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/projects`);
  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();

  const idea = `E2E черновик ${Date.now()}`;
  await page.getByRole("button", { name: "Предложить идею", exact: true }).click();
  await page.getByPlaceholder("Мы делаем [что] для [кого], чтобы [зачем]").fill(idea);
  await page.getByRole("button", { name: "Начать конструктор →" }).click();

  // The idea was saved by project creation, so the constructor resumes at
  // the first unanswered step: title.
  await expect(page.getByText("Теория шага", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Как будет называться проект?" })).toBeVisible();
  await expect(page.getByText("Что написать", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Получить подсказку", exact: true })).toBeVisible();

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
