import { expect, test } from "@playwright/test";

const LEADER_TELEGRAM_ID = 900002;

async function enterLeaderWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${LEADER_TELEGRAM_ID}`);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Режим лидера.*Рабочие инструменты и управление.*Открыть/ }).click();
  await expect(page.getByRole("heading", { name: "Режим лидера" })).toBeVisible();
}

test("leader media request panel shows clear package steps", async ({ page }) => {
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  await page.route("**/api/v1/events?scope=all", (route) => route.fulfill({
    json: [
      {
        id: 11,
        title: "E2E Future Media Event",
        description: "",
        short_description: null,
        full_description: null,
        event_date: tomorrow,
        event_time: "18:00",
        end_time: null,
        location: "Yerevan",
        address: null,
        format: "offline",
        attendance_mode: "offline",
        category: null,
        organizer: null,
        participant_value: null,
        contact: null,
        chat_url: null,
        points_for_visit: 10,
        project_id: null,
        status: "published",
        display_status: "published",
        participant_limit: null,
        registered_count: 0,
        available_places: "без лимита",
        remaining_count: null,
        registration_status: null,
        waitlist_enabled: false,
        registration_required: true,
        registration_close_at: null,
        can_register: true,
        program: [],
        participant_tasks: [],
        poster_url: null,
      },
      {
        id: 12,
        title: "E2E Past Media Event",
        description: "",
        short_description: null,
        full_description: null,
        event_date: "2020-01-01",
        event_time: "18:00",
        end_time: null,
        location: "Yerevan",
        address: null,
        format: "offline",
        attendance_mode: "offline",
        category: null,
        organizer: null,
        participant_value: null,
        contact: null,
        chat_url: null,
        points_for_visit: 10,
        project_id: null,
        status: "completed",
        display_status: "completed",
        participant_limit: null,
        registered_count: 0,
        available_places: "без лимита",
        remaining_count: null,
        registration_status: null,
        waitlist_enabled: false,
        registration_required: true,
        registration_close_at: null,
        can_register: false,
        program: [],
        participant_tasks: [],
        poster_url: null,
      },
    ],
  }));
  await enterLeaderWorkspace(page);
  await page.getByRole("button", { name: /Медиа-запрос/ }).click();
  await expect(page.getByRole("heading", { name: "Медиа-запрос" })).toBeVisible();
  await expect(page.getByText(/заказ материала, не пост в канал/)).toBeVisible();
  const select = page.locator("select");
  await expect(select.locator("option", { hasText: "E2E Future Media Event" })).toHaveCount(1);
  await expect(select.locator("option", { hasText: "E2E Past Media Event" })).toHaveCount(0);
  await select.selectOption({ label: `${tomorrow} · E2E Future Media Event` });
  await expect(page.getByText("Заказать медиа команде")).toBeVisible();
  await expect(page.getByText("1. Пакет", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "3. Отправить в Медиа" })).toBeVisible();
});

test("leader overview shows real task status labels", async ({ page }) => {
  await page.route("**/api/v1/leader/overview", (route) => route.fulfill({
    json: {
      departments: [],
      directions: [],
      participants: [],
      events: [],
      projects: [],
      tasks: [
        { id: 1, title: "E2E published task", status: "published", deadline: "2026-12-01T12:00:00Z", points: 80, assignee_id: null },
        { id: 2, title: "E2E review task", status: "review", deadline: "2026-12-02T12:00:00Z", points: 40, assignee_id: 1 },
      ],
    },
  }));
  await enterLeaderWorkspace(page);
  await page.getByRole("button", { name: /Моя команда/ }).click();
  await expect(page.getByText("Открыт набор · 80 баллов")).toBeVisible();
  await expect(page.getByText("На проверке · 40 баллов")).toBeVisible();
  await expect(page.getByText(/Статус обновлён/)).toHaveCount(0);
});

test("leader opens the separate workspace and creates a new open task", async ({ page }) => {
  await enterLeaderWorkspace(page);

  await page.getByRole("button", { name: /Задачи на проверке/ }).click();
  await expect(page.getByRole("heading", { name: "Задачи на проверке" })).toBeVisible();
  await page.getByRole("button", { name: "Новая открытая задача" }).click();

  const taskTitle = `E2E задача ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(taskTitle);
  await page.getByPlaceholder("Описание").fill("Создано E2E-тестом лидера.");
  const futureDeadline = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16);
  await page.locator('input[type="datetime-local"]').fill(futureDeadline);
  await page.getByRole("button", { name: "Опубликовать" }).click();
  await expect(page.getByText(taskTitle)).toBeVisible();
});

test("leader Пульс недели keeps system facts separate and persists subjective weekly assessment", async ({ page }) => {
  await enterLeaderWorkspace(page);
  await page.getByRole("button", { name: /Пульс недели/ }).click();

  await expect(page.getByRole("heading", { name: "Пульс недели" })).toBeVisible();
  await expect(page.getByText("Система уже знает", { exact: true })).toBeVisible();
  await expect(page.getByText(/Эти показатели формируются системой и не редактируются лидером/)).toBeVisible();
  await expect(page.getByText("Команда", { exact: true })).toBeVisible();
  await expect(page.getByText("Просрочено", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Нужно внимание" }).click();
  await page.getByLabel("Темп").fill("4");
  await page.getByLabel("Ясность").fill("4");
  await page.getByLabel("Нагрузка").fill("3");
  await page.getByText("Главный результат недели").locator("..").getByRole("textbox").fill("E2E: команда синхронизирована");
  await page.getByText("Следующий приоритет").locator("..").getByRole("textbox").fill("E2E: закрыть следующий результат");
  await page.getByText("Что требует внимания").locator("..").getByRole("textbox").fill("E2E: держим темп");

  const submit = page.getByRole("button", { name: /Отправить Пульс недели|Обновить Пульс недели/ });
  await submit.click();
  await expect(page.getByText(/Последняя отправка:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Обновить Пульс недели" })).toBeVisible();
});
