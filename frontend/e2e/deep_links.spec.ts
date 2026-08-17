import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;
const ADMIN_TELEGRAM_ID = 900003;

test("eraPath query opens Projects when Telegram provides no fragment", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}&eraPath=projects`);

  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
  await expect(page.getByText("Начните с одной мысли")).toBeVisible();
});

test("fresh Telegram eraPath overrides a stale cached hash", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}&eraPath=projects#/events`);

  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
  await expect(page).toHaveURL(/#\/projects$/);
  await expect(page).not.toHaveURL(/eraPath=/);
});

test("eraPath admin opens the separate Admin workspace directly", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}&eraPath=admin`);

  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Вот что происходит в ЭРА сегодня" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Разделы управления ЭРА" })).toBeVisible();
  await expect(page).toHaveURL(/#\/admin$/);
});

test("#/tasks deep link opens the task surface directly", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/tasks`);

  await expect(page.getByRole("heading", { name: "Задачи" })).toBeVisible();
  await expect(page.getByText(/Пока нет задач в этом разделе/)).toBeVisible();
  await expect(page).toHaveURL(/#\/tasks$/);
});

test("#/events deep link opens the Events tab", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/events`);

  await expect(page.getByRole("heading", { name: "События" })).toBeVisible();
  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();
});

test("#/opportunities deep link opens Community on offers", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/opportunities`);

  // The Opportunities redesign (recognition points as reputation, not a
  // spendable store -- see CommunityScreen.tsx) collapsed every section
  // under one shared "Возможности" heading; there is no longer a
  // per-section "Предложения" title.
  await expect(page.getByRole("heading", { name: "Возможности" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Фильтр" })).toBeVisible();
});

// auctions/rewards/surveys are legacy-routable (old notifications/deep
// links must keep working) but no longer have their own per-section
// heading -- they render under the same shared "Возможности" title as
// every other Opportunities section.
for (const hash of ["auctions", "rewards", "surveys"] as const) {
  test(`#/${hash} deep link opens its Community feature`, async ({ page }) => {
    await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/${hash}`);
    await expect(page.getByRole("heading", { name: "Возможности" })).toBeVisible();
  });
}

test("community navigation stays synchronized with browser history", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/community`);
  // Auctions/rewards are intentionally no longer primary community
  // navigation (see CommunityScreen.tsx) -- use a card that still is.
  await page.getByText("Опросы", { exact: true }).first().click();
  await expect(page).toHaveURL(/#\/surveys$/);
  await expect(page.getByRole("heading", { name: "Возможности" })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/#\/community$/);
  await expect(page.getByRole("heading", { name: "Сообщество" })).toBeVisible();
});
