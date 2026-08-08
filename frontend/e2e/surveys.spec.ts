import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const PARTICIPANT_TELEGRAM_ID = 900001;

test("admin creates and sends a survey; the participant answers it and the admin sees the response", async ({
  browser,
}) => {
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  const participantContext = await browser.newContext();
  const participantPage = await participantContext.newPage();

  try {
    await adminPage.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
    await expect(adminPage.getByText("ЭРА / ADMIN")).toBeVisible();
    await adminPage.getByRole("button", { name: "Опросы" }).click();

    const surveyTitle = `E2E Survey ${Date.now()}`;
    await adminPage.getByPlaceholder("Название").fill(surveyTitle);
    await adminPage.getByPlaceholder("Вопросы, каждый на новой строке").fill("Вопрос один?\nВопрос два?");
    await adminPage.getByRole("button", { name: "Создать опрос" }).click();

    // A real create through the full stack, verified by the survey
    // appearing in the admin's own list after the screen refetches it.
    const surveyCard = adminPage.locator(".era-card", { hasText: surveyTitle });
    await expect(surveyCard).toBeVisible();
    await surveyCard.getByRole("button", { name: "Отправить" }).click();
    // exact match — "Отправлен: <date>" in the stats line below would also
    // substring-match a case-insensitive "отправлен" lookup.
    await expect(surveyCard.getByText("отправлен", { exact: true })).toBeVisible();

    await participantPage.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
    await participantPage.getByRole("button", { name: "Возможности" }).click();
    await participantPage.getByRole("button", { name: "Опросы" }).click();

    const participantCard = participantPage.locator(".era-card", { hasText: surveyTitle });
    await expect(participantCard).toBeVisible();
    await participantCard.getByRole("button", { name: "Ответить" }).click();
    const textareas = participantCard.locator("textarea");
    await textareas.nth(0).fill("Ответ на первый вопрос");
    await textareas.nth(1).fill("Ответ на второй вопрос");
    await participantCard.getByRole("button", { name: "Отправить" }).click();

    // A real submit through the full stack (API -> survey_service -> DB),
    // not a UI-only echo — verified by the survey now showing as completed
    // after the screen refetches it from the API.
    await expect(participantCard.getByText("пройден")).toBeVisible();

    await adminPage.reload();
    await adminPage.getByRole("button", { name: "Опросы" }).click();
    const refreshedCard = adminPage.locator(".era-card", { hasText: surveyTitle });
    await refreshedCard.getByRole("button", { name: /^Ответы/ }).click();
    await expect(refreshedCard.getByText("Ответ на первый вопрос")).toBeVisible();
  } finally {
    await adminContext.close();
    await participantContext.close();
  }
});
