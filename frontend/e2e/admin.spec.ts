import { expect, test } from "@playwright/test";

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
  await expect(page.getByRole("heading", { name: "Все показатели" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Вовлечённость.*показателей/ })).toBeVisible();
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
