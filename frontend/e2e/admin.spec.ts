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

  await expect(page.getByText("Здоровье ЭРА", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Два сигнала. Одна картина." })).toBeVisible();
  await expect(page.getByText("Показатели здоровья", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Показать все .* показателей/ })).toBeVisible();
});

test("overview KPI opens exact underlying rows", async ({ page }) => {
  await enterAdminWorkspace(page);

  const currentRoster = page.getByRole("button", { name: /Участники.*Открыть состав/ });
  await expect(currentRoster).toBeVisible();
  await currentRoster.click();

  await expect(page.getByRole("heading", { name: "Текущий состав" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Скачать эти .* строк.* в Excel/ })).toBeVisible();
});
