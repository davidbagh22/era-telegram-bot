import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const ADMIN_TELEGRAM_ID = 900003;

function profileTab(page: import("@playwright/test").Page) {
  return page
    .getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true });
}

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(profileTab(page)).toBeVisible();
  await profileTab(page).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Пульт руководителя", { exact: true })).toBeVisible();
}

test("admin enters management workspace and approves a pending applicant", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: /Заявки.*Новые регистрации и решения по ним/ }).click();

  const application = page.locator(".era-card", { hasText: "E2E Pending Applicant" });
  await expect(application).toBeVisible();
  await expect(application.getByText("Личные данные", { exact: true })).toBeVisible();
  await expect(application.getByText("Контакты", { exact: true })).toBeVisible();
  await expect(application.getByText("Учёба и деятельность", { exact: true })).toBeVisible();
  await expect(application.getByText("Интерес к ЭРА", { exact: true })).toBeVisible();
  await expect(application.getByText("Мотивация", { exact: true })).toBeVisible();
  await expect(application.getByText("Согласие и подача", { exact: true })).toBeVisible();

  await expect(application.getByText("Дата рождения", { exact: true })).toHaveCount(0);
  await expect(application.getByText("Telegram ID", { exact: true })).not.toBeVisible();
  await application.locator("summary").filter({ hasText: "Служебные сведения" }).click();
  await expect(application.getByText("Telegram ID", { exact: true })).toBeVisible();
  for (const width of [320, 430, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await application.getByRole("button", { name: "Одобрить" }).click();
  await expect(page.locator(".era-card", { hasText: "E2E Pending Applicant" })).not.toBeVisible();
});

test("admin overview is a simple leader control surface", async ({ page }) => {
  await enterAdminWorkspace(page);

  await expect(page.getByText("Пульт руководителя", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Что происходит в ЭРА" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Нужно решить" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Быстро сделать" })).toBeVisible();
  await expect(page.getByText("Регистрация и состав", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Аналитика/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Контроль" })).toHaveCount(0);
});

test("analytics expands from overview instead of a separate control hub", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: /Аналитика/ }).click();

  await expect(page.getByRole("heading", { name: "ЭРА одним взглядом" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Главное" })).toBeVisible();
  for (const name of ["Обзор", "Люди", "Деятельность", "Команда", "Возможности", "Отчёты"]) {
    await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
  }
  await expect(page.getByText("Публикации канала", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Люди", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Все показатели" })).toBeVisible();
  const engagement = page.locator("details.analytics-metric-group").filter({ has: page.locator("summary", { hasText: /Вовлечённость.*показателей/ }) });
  await engagement.locator("summary").click();
  await expect(engagement.getByText("Числитель:", { exact: false }).first()).toBeVisible();
});

test("analytics exports selected custom period as a complete PDF", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: /Аналитика/ }).click();
  await page.getByLabel("Период отчёта").selectOption("custom");
  const downloadButton = page.getByRole("button", { name: "↓ Скачать отчёт PDF" });
  await expect(downloadButton).toBeDisabled();
  await page.getByLabel("Начало периода").fill("2026-01-01");
  await page.getByLabel("Конец периода").fill("2026-10-21");
  const responsePromise = page.waitForResponse((response) =>
    response.request().method() === "GET" && response.url().includes("executive-report.pdf"));
  const downloadPromise = page.waitForEvent("download");
  await downloadButton.click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("application/pdf");
  expect(response.url()).toContain("start_date=2026-01-01");
  expect(response.url()).toContain("end_date=2026-10-21");
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("ERA_analytics_2026-01-01_2026-10-21.pdf");
  const path = await download.path();
  expect(path).not.toBeNull();
  const pdf = await readFile(path!);
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  expect(pdf.length).toBeGreaterThan(10_000);
  await expect(downloadButton).toBeEnabled();
  for (const width of [320, 430, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const heading = await page.getByRole("heading", { name: "ЭРА одним взглядом" }).boundingBox();
    expect(heading?.width).toBeGreaterThan(200);
  }
});

test("analytics quick action opens the actual tasks workspace", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: /Аналитика/ }).click();
  await page.getByRole("button", { name: "Открыть задания →", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Дать работу или проверить результат" })).toBeVisible();
});

test("overview KPI opens exact underlying rows", async ({ page }) => {
  await enterAdminWorkspace(page);

  const currentRoster = page.getByRole("button", { name: /Участники.*Открыть состав/ });
  await expect(currentRoster).toBeVisible();
  await currentRoster.click();

  await expect(page.getByRole("heading", { name: "Текущий состав" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Скачать эти .* строк.* в Excel/ })).toBeVisible();
});

test("leaders workcenter creates a task and confirms a separate leader status", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди", exact: true }).click();
  await page.getByRole("button", { name: /Лидеры.*Команда, задачи, рассылки и Пульс/ }).click();
  for (const name of ["Команда", "Задачи", "Рассылки", "Пульс"]) {
    await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "➕ Новая задача", exact: true }).click();
  const title = `E2E поручение ${Date.now()}`;
  await page.getByLabel("Что сделать", { exact: true }).fill(title);
  await page.getByLabel("Зачем и какой результат нужен").fill("Проверить общий процесс");
  await page.getByRole("button", { name: "Предпросмотр", exact: true }).click();
  await page.getByRole("button", { name: "Создать задачу", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Задача сохранена");
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Команда", exact: true }).click();
  await page.getByLabel("Поиск участника").fill("E2E Participant");
  await page.getByRole("button", { name: "Найти / назначить лидера", exact: true }).click();
  await page.getByRole("button", { name: "Назначить лидером", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Подтвердите изменение" })).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Статус обновлён");
  await expect(page.getByRole("button", { name: "Снять статус лидера", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Снять статус лидера", exact: true }).click();
  await page.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(page.getByRole("button", { name: "Назначить лидером", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Рассылки", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Сообщение команде" })).toBeVisible();
});
