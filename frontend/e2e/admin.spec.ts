import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(page.getByRole("button", { name: "Профиль" })).toBeVisible();
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin enters separate management workspace and approves a pending applicant", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: "Заявки" }).click();

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

test("admin control has analytics system and maintenance as separate destinations", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Контроль" }).click();
  await expect(page.getByRole("button", { name: /Аналитика/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Состояние системы/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Обслуживание/ })).toBeVisible();
});

test("analytics shows ERA efficiency and opens the real records behind each metric", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Контроль" }).click();
  await page.getByRole("button", { name: /Аналитика/ }).click();

  await expect(page.getByText("Эффективность ЭРА", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Что делать дальше" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Открыть или выгрузить" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Полный отчёт ЭРА/ })).toBeVisible();

  const participantsMetric = page.getByRole("button", { name: /Участники.*Люди, статусы и динамика базы/ });
  await expect(participantsMetric).toBeVisible();
  await participantsMetric.click();

  await expect(page.getByRole("heading", { name: "Участники" })).toBeVisible();
  await expect(page.getByText("Записей в системе", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Таблица CSV/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Полный XLSX/ })).toBeVisible();
  await expect(page.locator(".era-card").filter({ hasText: /participant|admin|leader|activist/i }).first()).toBeVisible();
});
