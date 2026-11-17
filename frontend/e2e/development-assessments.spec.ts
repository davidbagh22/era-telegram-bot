import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant completes WHO-5 through My Vector and sees the saved result", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  const vectorEntry = page.getByRole("button", { name: /Мой вектор/ });
  await expect(vectorEntry).toBeVisible();
  await vectorEntry.click();

  const consentButton = page.getByRole("button", { name: "Понятно, продолжить" });
  const vectorHeading = page.getByRole("heading", { name: "Где ты сейчас и куда двигаться дальше" });
  await expect(consentButton.or(vectorHeading)).toBeVisible();
  if (await consentButton.isVisible().catch(() => false)) await consentButton.click();

  await expect(vectorHeading).toBeVisible();
  await page.getByRole("button", { name: /исследования/i }).click();
  await expect(page.getByRole("heading", { name: "Все исследования" })).toBeVisible();

  await page.getByRole("button", { name: /Как мне сейчас\?/ }).click();
  await expect(page.getByRole("heading", { name: "Как мне сейчас?" })).toBeVisible();
  await page.getByRole("button", { name: "Начать" }).click();

  for (let index = 0; index < 4; index += 1) {
    await expect(page.getByRole("button", { name: "Всё время" })).toBeVisible();
    await page.getByRole("button", { name: "Всё время" }).click();
  }

  // Failed last-answer save must leave the question for retry (not open review).
  await page.route("**/api/v1/development/assessment-sessions/*/answers", async (route) => {
    if (route.request().method() === "PATCH") {
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "save_failed" }) });
      return;
    }
    await route.continue();
  });
  await expect(page.getByRole("button", { name: "Всё время" })).toBeVisible();
  await page.getByRole("button", { name: "Всё время" }).click();
  await expect(page.getByRole("alert")).toContainText("Ответ не сохранился");
  await expect(page.getByText("ГОТОВО К РЕЗУЛЬТАТУ")).toHaveCount(0);
  await page.unroute("**/api/v1/development/assessment-sessions/*/answers");

  await page.getByRole("button", { name: "Всё время" }).click();
  await expect(page.getByText("ГОТОВО К РЕЗУЛЬТАТУ")).toBeVisible();
  // Re-checking the last answer must still return to the submit screen.
  await page.getByRole("button", { name: "← Проверить последний ответ" }).click();
  await expect(page.getByRole("button", { name: "Всё время" })).toBeVisible();
  await page.getByRole("button", { name: "Всё время" }).click();
  await expect(page.getByText("ГОТОВО К РЕЗУЛЬТАТУ")).toBeVisible();
  await page.getByRole("button", { name: "Получить результат" }).click();
  await expect(page.getByText("ТВОЙ ПРОФИЛЬ ЭРА")).toBeVisible();
  await expect(page.getByText(/100 из 100/)).toBeVisible();
  await expect(page.getByText(/Что мне действительно интересно/)).toBeVisible();
});
