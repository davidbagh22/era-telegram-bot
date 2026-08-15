import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("project constructor keeps the typed answer visible when one PATCH fails", async ({ page }) => {
  let failedOnce = false;
  await page.route("**/api/v1/projects/*", async (route) => {
    if (route.request().method() === "PATCH" && !failedOnce) {
      failedOnce = true;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "forced_constructor_regression" }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}&eraPath=projects`);
  await expect(page.getByText("Начните с одной мысли")).toBeVisible();

  await page.getByPlaceholder("Мы делаем [что] для [кого], чтобы [зачем]").fill("Тестовый проект конструктора");
  await page.getByRole("button", { name: "Начать конструктор →" }).click();

  const answer = page.getByPlaceholder("Ваш ответ…");
  await expect(answer).toBeVisible();
  await answer.fill("Название, которое нельзя потерять");
  await page.getByRole("button", { name: "Сохранить и дальше →" }).click();

  await expect(page.getByText("Ответ не потерян", { exact: true })).toBeVisible();
  await expect(answer).toHaveValue("Название, которое нельзя потерять");
  await expect(page.getByText("сохранён на устройстве", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Повторить сохранение" }).click();
  await expect(page.getByText("Ответ не потерян", { exact: true })).toBeHidden();
  await expect(page.getByText(/шаг 3 из/i)).toBeVisible();
});
