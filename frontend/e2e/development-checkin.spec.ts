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

async function currentSurface(page: Page): Promise<"question" | "context" | "result"> {
  const answer = page.getByRole("button", { name: "Скорее да", exact: true });
  const context = page.getByRole("heading", { name: "Контекст месяца" });
  const result = page.getByText("ТВОЙ ФОКУС МЕСЯЦА");

  await expect(answer.or(context).or(result)).toBeVisible();
  if (await result.isVisible().catch(() => false)) return "result";
  if (await context.isVisible().catch(() => false)) return "context";
  return "question";
}

async function finishRemainingQuestions(page: Page): Promise<"context" | "result"> {
  for (let index = 0; index < 16; index += 1) {
    const surface = await currentSurface(page);
    if (surface === "context" || surface === "result") return surface;
    await page.getByRole("button", { name: "Скорее да", exact: true }).click();
  }
  throw new Error("Check-in did not reach context/result within the expected question limit");
}

function answeredCount(text: string | null): number {
  const match = text?.match(/^(\d+)\s+из\s+\d+/);
  return match ? Number(match[1]) : 0;
}

test("monthly check-in resumes from server answers and produces one focus", async ({ page }) => {
  await openVector(page);
  await openCurrentCheckin(page);

  if (!(await page.getByText("ТВОЙ ФОКУС МЕСЯЦА").isVisible().catch(() => false))) {
    for (let index = 0; index < 2; index += 1) {
      const surface = await currentSurface(page);
      if (surface !== "question") break;
      await page.getByRole("button", { name: "Скорее да", exact: true }).click();
    }

    const surfaceBeforeLeave = await currentSurface(page);
    let savedAnswered = 0;
    if (surfaceBeforeLeave === "question") {
      const counter = page.getByText(/\d+ из \d+ · ещё около/);
      savedAnswered = answeredCount(await counter.textContent());
      expect(savedAnswered).toBeGreaterThan(0);
    }

    const continueLater = page.getByRole("button", { name: "Продолжить позже", exact: true });
    if (await continueLater.isVisible().catch(() => false)) await continueLater.click();

    // Reopen the Mini App from scratch. This is the actual product contract:
    // answers are restored from the backend rather than from local React state.
    await openVector(page);
    await openCurrentCheckin(page);

    const resumedSurface = await currentSurface(page);
    if (surfaceBeforeLeave === "question" && resumedSurface === "question") {
      const resumedCounter = page.getByText(/\d+ из \d+ · ещё около/);
      const resumedAnswered = answeredCount(await resumedCounter.textContent());
      expect(resumedAnswered).toBeGreaterThanOrEqual(savedAnswered);
      expect(resumedAnswered).toBeGreaterThan(0);
    } else if (surfaceBeforeLeave === "context") {
      expect(["context", "result"]).toContain(resumedSurface);
    }

    const finalSurface = resumedSurface === "result" ? "result" : await finishRemainingQuestions(page);

    if (finalSurface === "context") {
      await page.getByRole("button", { name: "учёба", exact: true }).click();
      await page.getByRole("button", { name: "уверенность", exact: true }).click();
      await page.getByRole("button", { name: "Получить мой результат", exact: true }).click();
    }
  }

  await expect(page.getByText("ТВОЙ ФОКУС МЕСЯЦА")).toBeVisible();
  await expect(page.getByRole("button", { name: "Почему?", exact: true })).toBeVisible();
  await expect(page.getByText("Администратор эту заметку не видит.")).toBeVisible();
});
