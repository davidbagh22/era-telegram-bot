import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const PARTICIPANT_TELEGRAM_ID = 900001;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin creates and sends a survey; the participant answers it and the admin sees the response", async ({ browser }) => {
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  const participantContext = await browser.newContext();
  const participantPage = await participantContext.newPage();

  try {
    await enterAdminWorkspace(adminPage);
    await adminPage.getByRole("button", { name: "Связь" }).click();
    await adminPage.getByRole("button", { name: "Опросы" }).click();

    const surveyTitle = `E2E Survey ${Date.now()}`;
    await adminPage.getByPlaceholder("Название").fill(surveyTitle);
    await adminPage.getByPlaceholder("Вопросы, каждый на новой строке").fill("Вопрос один?\nВопрос два?");
    await adminPage.getByRole("button", { name: "Создать опрос" }).click();

    const surveyCard = adminPage.locator(".era-card", { hasText: surveyTitle });
    await expect(surveyCard).toBeVisible();
    await surveyCard.getByRole("button", { name: "Отправить" }).click();
    await expect(surveyCard.getByText("отправлен", { exact: true })).toBeVisible();

    await participantPage.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
    await participantPage.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Сообщество" }).click();
    await participantPage.getByRole("button", { name: "Опросы" }).click();
    const participantCard = participantPage.locator(".era-card", { hasText: surveyTitle });
    await expect(participantCard).toBeVisible();
    await participantCard.getByRole("button", { name: "Ответить" }).click();
    const textareas = participantCard.locator("textarea");
    await textareas.nth(0).fill("Ответ на первый вопрос");
    await textareas.nth(1).fill("Ответ на второй вопрос");
    await participantCard.getByRole("button", { name: "Отправить" }).click();
    await expect(participantCard.getByText("пройден")).toBeVisible();

    await enterAdminWorkspace(adminPage);
    await adminPage.getByRole("button", { name: "Связь" }).click();
    await adminPage.getByRole("button", { name: "Опросы" }).click();
    const refreshedCard = adminPage.locator(".era-card", { hasText: surveyTitle });
    await refreshedCard.getByRole("button", { name: /^Ответы/ }).click();
    await expect(refreshedCard.getByText("Ответ на первый вопрос")).toBeVisible();
  } finally {
    await adminContext.close();
    await participantContext.close();
  }
});