import { expect, test, type Page } from "@playwright/test";

// Critical Mini App journeys toward 10/10 acceptance. Fixtures are isolated
// users/events/tasks from scripts/e2e_seed.py (900021–900024) so these specs
// never contend with participant.spec / event_cancel_confirmation.spec over
// the shared "E2E тестовое мероприятие" registration row. No real Telegram
// broadcasts — DEV_AUTH + throwaway SQLite only.

const HOME_REGISTER_TELEGRAM_ID = 900024;
const WAITLIST_CLAIMER_TELEGRAM_ID = 900022;
const TASK_CLAIMER_TELEGRAM_ID = 900023;

async function openEventFromActivity(page: Page, title: string) {
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Участие" }).click();
  await page.getByRole("tab", { name: "События" }).click();
  await expect(page.getByRole("tab", { name: "События", selected: true })).toBeVisible();
  const card = page.locator(".era-card", { hasText: title }).first();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Открыть событие" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
}

test("Home → event → register → cancel keeps confirmation copy paths", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${HOME_REGISTER_TELEGRAM_ID}`);
  await expect(page.getByText("Вот что сейчас важнее всего.", { exact: true })).toBeVisible();

  const board = page.getByRole("region", { name: "Афиша ЭРА" });
  // Home board cards are clickable surfaces (no separate «Открыть событие» CTA).
  await board.getByText("E2E путь Home→регистрация").click();

  await expect(page.getByRole("heading", { name: "E2E путь Home→регистрация" })).toBeVisible();
  await page.getByRole("button", { name: "Участвовать" }).click();
  await expect(page.getByRole("heading", { name: "Место за вами" })).toBeVisible();
  await expect(page.getByText("✓ Вы участвуете").first()).toBeVisible();
  await page.getByRole("button", { name: "Готово" }).click();

  const cancelTrigger = page.getByRole("button", { name: "Отказаться", exact: true });
  await expect(cancelTrigger).toBeVisible();
  await cancelTrigger.click();
  await expect(page.getByText("Отказаться от участия?")).toBeVisible();
  await page.getByRole("button", { name: "Отказаться", exact: true }).last().click();
  await expect(page.getByRole("button", { name: "Участвовать" })).toBeVisible();
  await expect(page.getByText("Участие отменено")).toBeVisible();
});

test("full event → waitlist CTA → queue copy → cancel from waitlist", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${WAITLIST_CLAIMER_TELEGRAM_ID}`);
  await openEventFromActivity(page, "E2E лист ожидания");

  await expect(page.getByText("Осталось 0")).toBeVisible();
  const waitlistCta = page.getByRole("button", { name: "Встать в лист ожидания" });
  await expect(waitlistCta).toBeVisible();
  await waitlistCta.click();

  // Waitlist opens its own success sheet (not «Место за вами»).
  // Scope copy to the dialog — detail still mounts «Если место освободится…» behind it.
  const waitlistSheet = page.getByRole("dialog", { name: "Вы в листе ожидания" });
  await expect(waitlistSheet).toBeVisible();
  await expect(waitlistSheet.getByText(/если оно освободится/i)).toBeVisible();
  await waitlistSheet.getByRole("button", { name: "Понятно" }).click();

  await expect(page.getByText("Вы в листе ожидания").first()).toBeVisible();
  await expect(page.getByText(/Лист ожидания/)).toBeVisible();

  // Dock CTA for waitlist is «Покинуть», not «Отказаться».
  await page.getByRole("button", { name: "Покинуть", exact: true }).click();
  await expect(page.getByText("Покинуть лист ожидания?")).toBeVisible();
  await page.getByRole("button", { name: "Остаться в очереди" }).click();
  await expect(page.getByText("Вы в листе ожидания").first()).toBeVisible();

  await page.getByRole("button", { name: "Покинуть", exact: true }).click();
  await page.getByRole("button", { name: "Покинуть", exact: true }).last().click();
  await expect(page.getByRole("button", { name: "Встать в лист ожидания" })).toBeVisible();
  await expect(page.getByText("Вы покинули лист ожидания")).toBeVisible();
});

test("tasks list → detail → claim SOLO assignment", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${TASK_CLAIMER_TELEGRAM_ID}#/tasks`);
  await expect(page.getByRole("heading", { name: "Задания" })).toBeVisible();

  // Default scope is «Для тебя»; seeded challenge should land there.
  // Cards expose «Взять» + «Подробнее» (claim from list is allowed; we open detail).
  const card = page.locator(".era-card", { hasText: "E2E открытое задание" }).first();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Подробнее" }).click();

  await expect(page.getByRole("heading", { name: "E2E открытое задание" })).toBeVisible();
  await expect(page.getByText("Что нужно сделать")).toBeVisible();
  await expect(page.getByText(/Изолированная проверка: открыть детали/)).toBeVisible();
  await expect(page.getByText("Короткий текстовый отчёт", { exact: true })).toBeVisible();
  await expect(page.getByText("Соло")).toBeVisible();

  await page.getByRole("button", { name: "Взять задачу" }).click();
  // After self-serve claim the CTA disappears. «Отправить результат в боте» only
  // renders when BOT_USERNAME is set (often empty in local/CI) — do not assert it.
  await expect(page.getByRole("button", { name: "Взять задачу" })).toHaveCount(0);
  await expect(page.getByText("Что нужно сделать")).toBeVisible();

  await page.getByRole("button", { name: "← К заданиям" }).click();
  await page.getByRole("button", { name: /Показать:/ }).click();
  await page.getByRole("button", { name: /^Мои/ }).click();
  await expect(page.getByText("E2E открытое задание")).toBeVisible();
});
