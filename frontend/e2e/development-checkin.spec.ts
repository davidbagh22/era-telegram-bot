import { expect, test, type Page } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

async function openVector(page: Page) {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: /Как ты изменился за последний месяц/ }).click();
  const consent = page.getByRole("button", { name: "Понятно, продолжить" });
  if (await consent.isVisible().catch(() => false)) await consent.click();
  await expect(page.getByRole("heading", { name: "Мой вектор" })).toBeVisible();
}

async function openCurrentCheckin(page: Page) {
  await page.getByRole("button", { name: /Посмотрим, что изменилось|Посмотреть результат месяца/ }).click();
}

async function finishRemainingQuestions(page: Page) {
  for (let index = 0; index < 12; index += 1) {
    if (await page.getByRole("heading", { name: "Контекст месяца" }).isVisible().catch(() => false)) return;
    if (await page.getByText("ТВОЙ ФОКУС МЕСЯЦА").isVisible().catch(() => false)) return;
    const answer = page.getByRole("button", { name: "Скорее да", exact: true });
    await expect(answer).toBeVisible();
    await answer.click();
  }
  throw new Error("Check-in did not reach context/result within the expected question limit");
}

test("monthly check-in resumes from server answers and produces one focus", async ({ page }) => {
  await openVector(page);
  await openCurrentCheckin(page);

  // Playwright retries reuse the seeded database. If a previous attempt already
  // completed this month's check-in, verify the persisted result instead of
  // pretending the user starts from an empty questionnaire again.
  if (!(await page.getByText("ТВОЙ ФОКУС МЕСЯЦА").isVisible().catch(() => false))) {
    for (let index = 0; index < 2; index += 1) {
      if (await page.getByRole("heading", { name: "Контекст месяца" }).isVisible().catch(() => false)) break;
      const answer = page.getByRole("button", { name: "Скорее да", exact: true });
      if (!(await answer.isVisible().catch(() => false))) break;
      await answer.click();
    }

    const contextReached = await page.getByRole("heading", { name: "Контекст месяца" }).isVisible().catch(() => false);
    const progress = page.locator('[aria-label^="Прогресс "]');
    const savedProgress = contextReached ? null : await progress.getAttribute("aria-label");

    const continueLater = page.getByRole("button", { name: "Продолжить позже", exact: true });
    if (await continueLater.isVisible().catch(() => false)) await continueLater.click();

    // Reopening the Mini App is the real product contract: answers must come
    // back from the server and the user must continue from the saved position.
    await openVector(page);
    await openCurrentCheckin(page);

    if (contextReached) {
      await expect(page.getByRole("heading", { name: "Контекст месяца" })).toBeVisible();
    } else if (savedProgress) {
      await expect(page.locator(`[aria-label="${savedProgress}"]`)).toBeVisible();
    }

    await finishRemainingQuestions(page);

    if (await page.getByRole("heading", { name: "Контекст месяца" }).isVisible().catch(() => false)) {
      await page.getByRole("button", { name: "учёба", exact: true }).click();
      await page.getByRole("button", { name: "уверенность", exact: true }).click();
      await page.getByRole("button", { name: "Получить мой результат", exact: true }).click();
    }
  }

  await expect(page.getByText("ТВОЙ ФОКУС МЕСЯЦА")).toBeVisible();
  await expect(page.getByRole("button", { name: "Почему?", exact: true })).toBeVisible();
  await expect(page.getByText("Администратор эту заметку не видит.")).toBeVisible();
});
