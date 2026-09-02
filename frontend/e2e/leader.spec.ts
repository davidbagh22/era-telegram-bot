import { expect, test } from "@playwright/test";

const LEADER_TELEGRAM_ID = 900002;

async function enterLeaderWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${LEADER_TELEGRAM_ID}`);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Пространство лидера.*Рабочие инструменты и управление.*Открыть/ }).click();
  await expect(page.getByRole("heading", { name: "Пространство лидера" })).toBeVisible();
}

test("leader opens the separate workspace and creates a new open task", async ({ page }) => {
  await enterLeaderWorkspace(page);

  await page.getByRole("button", { name: /Открытые задачи/ }).click();
  await expect(page.getByRole("heading", { name: "Открытые задачи" })).toBeVisible();
  await page.getByRole("button", { name: "Новая открытая задача" }).click();

  const taskTitle = `E2E задача ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(taskTitle);
  await page.getByPlaceholder("Описание").fill("Создано E2E-тестом лидера.");
  const futureDeadline = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16);
  await page.locator('input[type="datetime-local"]').fill(futureDeadline);
  await page.getByRole("button", { name: "Опубликовать" }).click();
  await expect(page.getByText(taskTitle)).toBeVisible();
});

test("leader Weekly Pulse keeps system facts separate and persists subjective weekly assessment", async ({ page }) => {
  await enterLeaderWorkspace(page);
  await page.getByRole("button", { name: /Weekly Pulse/ }).click();

  await expect(page.getByRole("heading", { name: "Weekly Pulse" })).toBeVisible();
  await expect(page.getByText("Система уже знает", { exact: true })).toBeVisible();
  await expect(page.getByText(/Эти показатели формируются системой и не редактируются лидером/)).toBeVisible();
  await expect(page.getByText("Команда", { exact: true })).toBeVisible();
  await expect(page.getByText("Просрочено", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Нужно внимание" }).click();
  await page.getByLabel("Темп").fill("4");
  await page.getByLabel("Ясность").fill("4");
  await page.getByLabel("Нагрузка").fill("3");
  await page.getByText("Главный результат недели").locator("..").getByRole("textbox").fill("E2E: команда синхронизирована");
  await page.getByText("Следующий приоритет").locator("..").getByRole("textbox").fill("E2E: закрыть следующий результат");
  await page.getByText("Что требует внимания").locator("..").getByRole("textbox").fill("E2E: держим темп");

  const submit = page.getByRole("button", { name: /Отправить Weekly Pulse|Обновить Weekly Pulse/ });
  await submit.click();
  await expect(page.getByText(/Последняя отправка:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Обновить Weekly Pulse" })).toBeVisible();
});
