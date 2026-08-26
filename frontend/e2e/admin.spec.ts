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
  await expect(page.getByRole("heading", { name: "ЭРА сейчас — вся картина сразу" })).toBeVisible();
}

test("admin lands directly on one command center with analytics and operations", async ({ page }) => {
  await enterAdminWorkspace(page);

  await expect(page.getByRole("heading", { name: "Главные показатели" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Требует внимания" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Все рабочие зоны" })).toBeVisible();
  await expect(page.getByText("Эффективность", { exact: true })).toBeVisible();
  await expect(page.getByText("Пульс", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Что делать дальше" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Открыть или выгрузить" })).toBeVisible();

  // Regression: analytics/system/maintenance must never become a second menu
  // layer again. They are embedded into the command center.
  await expect(page.getByRole("button", { name: "Контроль", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Аналитика", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Обслуживание", exact: true })).toHaveCount(0);
});

test("admin opens pending applications directly from command center and approves one", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: /Новые заявки/ }).click();
  await expect(page.getByRole("heading", { name: "Новые заявки" })).toBeVisible();

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
  await page.getByRole("button", { name: "← Пульт ЭРА" }).click();
  await expect(page.getByRole("heading", { name: "ЭРА сейчас — вся картина сразу" })).toBeVisible();
});

test("embedded analytics opens real records without a separate analytics window", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Вся аналитика ↓" }).click();

  await expect(page.getByText("Эффективность", { exact: true })).toBeVisible();
  await expect(page.getByText("Пульс", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Здоровье организации/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Полный отчёт ЭРА/ })).toBeVisible();

  const participantsMetric = page.getByRole("button", { name: /Участники.*Люди, статусы и динамика базы/ });
  await expect(participantsMetric).toBeVisible();
  await participantsMetric.click();

  await expect(page.getByRole("heading", { name: "Участники" })).toBeVisible();
  await expect(page.getByText("Записей в системе", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "↓ XLSX", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Полный XLSX/ })).toBeVisible();
  await expect(page.locator(".era-card").filter({ hasText: /participant|admin|leader|activist/i }).first()).toBeVisible();
});

test("overview KPI opens exact underlying rows instead of a generic people menu", async ({ page }) => {
  await enterAdminWorkspace(page);

  const currentRoster = page.getByRole("button", { name: /Участники.*Подтверждённый состав/ });
  await expect(currentRoster).toBeVisible();
  await currentRoster.click();

  await expect(page.getByRole("heading", { name: "Текущий состав" })).toBeVisible();
  await expect(page.getByText(/Список построен тем же правилом, что и KPI на главной/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Скачать эти .* строк в Excel/ })).toBeVisible();
});

test("technical diagnostics are inline and do not leave the admin home", async ({ page }) => {
  await enterAdminWorkspace(page);
  const diagnostics = page.getByText("Техническая диагностика · API / Bot / Telegram / DB / Backup", { exact: true });
  await diagnostics.scrollIntoViewIfNeeded();
  await diagnostics.click();
  await expect(page.getByText(/API|База данных|Backup/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "ЭРА сейчас — вся картина сразу" })).toBeVisible();
});
