import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const ADMIN_TELEGRAM_ID = 900003;

function profileTab(page: import("@playwright/test").Page) {
  return page
    .getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Я", exact: true });
}

async function openMoreTools(page: import("@playwright/test").Page) {
  const more = page.getByRole("button", { name: /^Ещё/ });
  if ((await more.getAttribute("aria-expanded")) !== "true") await more.click();
}

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(profileTab(page)).toBeVisible();
  await profileTab(page).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Пульт руководителя", { exact: true })).toBeVisible();
}

test("career reviewer sees only safe legacy evidence links", async ({ page }) => {
  // Mock responses in the local Playwright browser; never create production rows.
  await page.route("**/api/v1/admin/career/pending", (route) => route.fulfill({ json: [
    { id: -9101, user_id: -1, user_name: "Local fixture", title: "Unsafe legacy evidence",
      organization: "", description: "", url: "javascript:alert(1)", has_file: false, status: "pending" },
    { id: -9102, user_id: -1, user_name: "Local fixture", title: "Safe evidence",
      organization: "", description: "", url: "https://example.org/proof", has_file: false, status: "pending" },
  ] }));
  await page.route("**/api/v1/admin/career/recommendations/pending", (route) => route.fulfill({ json: [] }));
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: /Портфолио и рекомендации/ }).click();
  await expect(page.getByText("Unsafe legacy evidence")).toBeVisible();
  const links = page.getByRole("link", { name: "Открыть источник ↗" });
  await expect(links).toHaveCount(1);
  await expect(links).toHaveAttribute("href", "https://example.org/proof");
});

test("admin enters management workspace and approves a pending applicant", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: /Заявки.*Новые регистрации и решения по ним/ }).click();

  const application = page.locator(".era-card", { hasText: "E2E Pending Applicant" });
  await expect(application).toBeVisible();
  await expect(application.getByText("Личные данные", { exact: true })).toBeVisible();
  await expect(application.getByText("Контакты", { exact: true })).toBeVisible();
  await expect(application.getByText("Учёба и деятельность", { exact: true })).toBeVisible();
  await expect(application.getByText("Интерес к ЭРА", { exact: true })).toBeVisible();
  await expect(application.getByText("Мотивация", { exact: true })).toBeVisible();
  await expect(application.getByText("Согласие и подача", { exact: true })).toBeVisible();

  await expect(application.getByText("Дата рождения", { exact: true })).toHaveCount(0);
  await expect(application.getByText("номер Telegram", { exact: true })).not.toBeVisible();
  await application.locator("summary").filter({ hasText: "Служебные сведения" }).click();
  await expect(application.getByText("номер Telegram", { exact: true })).toBeVisible();
  for (const width of [320, 430, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await application.getByRole("button", { name: "Одобрить" }).click();
  await expect(page.locator(".era-card", { hasText: "E2E Pending Applicant" })).not.toBeVisible();
});

test("admin overview is a simple leader control surface", async ({ page }) => {
  await enterAdminWorkspace(page);

  await expect(page.getByText("Пульт руководителя", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Что происходит в ЭРА" })).toBeVisible();

  const quick = page.getByTestId("admin-quick-actions");
  await expect(quick.getByRole("button", { name: /Рассылка/ })).toBeVisible();
  await expect(quick.getByRole("button", { name: /Задание/ })).toBeVisible();
  await expect(quick.getByRole("button", { name: /Мероприятие/ })).toBeVisible();

  const analytics = page.getByTestId("admin-analytics-summary");
  await expect(analytics.getByRole("button", { name: /Участники/ })).toBeVisible();
  await expect(analytics.getByRole("button", { name: /Активные/ })).toBeVisible();
  await expect(analytics.getByRole("button", { name: /Аналитика/ })).toBeVisible();

  const primary = page.getByTestId("admin-primary-actions");
  await expect(primary.getByRole("button")).toHaveCount(3);
  await expect(primary.getByRole("button", { name: /^Мероприятия/ })).toBeVisible();
  await expect(primary.getByRole("button", { name: /^Заявки/ })).toBeVisible();
  await expect(primary.getByRole("button", { name: /^Задачи/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Очередь решений/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Списки участников", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Последние записи" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Решить сегодня" })).toHaveCount(0);

  await openMoreTools(page);
  await expect(page.getByRole("heading", { name: "Решить сегодня" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Быстро сделать" })).toBeVisible();
  await expect(page.getByText("Регистрация и состав", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Контроль" })).toHaveCount(0);
});

test("overview shows pending applications count and the latest registrations", async ({ page }) => {
  await page.route("**/api/v1/admin/dashboard", (route) => route.fulfill({
    json: { metrics: { current_roster: 10, users_pending: 4 }, attention_total: 4 },
  }));
  await page.route("**/api/v1/admin/events/recent-registrations**", (route) => route.fulfill({ json: [
    { registration_id: 2, event_id: 7, event_title: "Мок-встреча", participant_id: 3, participant_name: "Мок Новый", status: "registered", registered_at: "2026-11-20T12:05:00+00:00" },
    { registration_id: 1, event_id: 7, event_title: "Мок-встреча", participant_id: 2, participant_name: "Мок Прежний", status: "registered", registered_at: "2026-11-20T12:00:00+00:00" },
  ] }));
  await enterAdminWorkspace(page);
  await expect(page.getByTestId("admin-primary-actions").getByRole("button", { name: /^Заявки.*4$/ })).toBeVisible();
  const items = page.getByRole("region", { name: "Последние записи" }).getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.first()).toContainText("Мок Новый");
  await expect(items.first()).toContainText("Мок-встреча");
});

test("overview shows task and support queues and opens their resolvers", async ({ page }) => {
  await page.route("**/api/v1/admin/dashboard", route => route.fulfill({ json: {
    metrics: { current_roster: 69, tasks_attention: 7, questions: 1 }, attention_total: 8,
  } }));
  await page.route("**/api/v1/admin/decision-queue", route => route.fulfill({ json: {
    tasks: [], decisions: [], total: 0,
  } }));
  await enterAdminWorkspace(page);
  // The Telegram SDK exists in the test browser, but has no native host.
  // Capture the host call instead of waiting for an unrelated browser popup.
  await page.evaluate(() => {
    window.Telegram.WebApp.openTelegramLink = (url: string) => {
      document.body.dataset.nativeQueueUrl = url;
    };
    window.Telegram.WebApp.close = () => { document.body.dataset.nativeQueueClosed = "true"; };
  });
  await expect(page.getByRole("button", { name: /8 требуют внимания/ })).toBeVisible();
  await openMoreTools(page);
  await expect(page.getByText("Очередь чистая ✓", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: /1 · Обращения ждут ответа/ }).click();
  await expect(page.locator("body")).toHaveAttribute("data-native-queue-url", "https://t.me/ERA_1bot?start=admin_question_attention");
  await expect(page.locator("body")).toHaveAttribute("data-native-queue-closed", "true");

  await page.getByRole("button", { name: /7 · Задачи требуют внимания/ }).click();
  await expect(page.getByRole("heading", { name: "Пункты, требующие решения" })).toBeVisible();
  await page.getByRole("button", { name: "Открыть в боте", exact: true }).click();
  await expect(page.locator("body")).toHaveAttribute("data-native-queue-url", "https://t.me/ERA_1bot?start=admin_task_attention");
});

test("command center quick actions jump directly to broadcast, task creation, and event creation", async ({ page }) => {
  await page.route("**/api/v1/admin/broadcast/options", (route) => route.fulfill({ json: { departments: [], directions: [] } }));
  await page.route("**/api/v1/admin/broadcast/preview-count**", (route) => route.fulfill({ json: { count: 0 } }));
  await page.route("**/api/v1/leader/open-tasks", (route) => route.fulfill({ json: [] }));

  await enterAdminWorkspace(page);
  await page.getByTestId("admin-quick-actions").getByRole("button", { name: /Рассылка/ }).click();
  await expect(page.getByRole("heading", { name: "Рассылки" })).toBeVisible();

  await page.getByRole("button", { name: "Обзор", exact: true }).click();
  await page.getByTestId("admin-quick-actions").getByRole("button", { name: /Задание/ }).click();
  await expect(page.getByRole("heading", { name: "Создать задание" })).toBeVisible();
  await expect(page.getByPlaceholder("Название")).toBeVisible();
  await expect(page.getByRole("button", { name: "Опубликовать", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Обзор", exact: true }).click();
  for (const width of [320, 430]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await page.getByTestId("admin-quick-actions").getByRole("button", { name: /Мероприятие/ }).click();
  await expect(page.getByRole("heading", { name: "Создать мероприятие" })).toBeVisible();
});

test("decision queue confirms deletion with audit undo and updates list", async ({ page }) => {
  let deletedDecision = false;
  let deletedTask = false;
  await page.route("**/api/v1/admin/decision-queue", (route) => route.fulfill({
    json: {
      decisions: deletedDecision ? [] : [{
        id: 701, type: "pulse_help", severity: "high", status: "open",
        text: "Тестовая эскалация на удаление", owner_name: "Лидер Тест",
        scope_type: "pulse", scope_id: 1, task_id: null, created_at: "2026-11-20T10:00:00Z",
      }],
      tasks: deletedTask ? [] : [{
        id: 801, title: "Просроченное тестовое задание", status: "in_progress",
        deadline: "2026-11-10T10:00:00Z", assignee_name: "Участник Тест",
        points: 50, reasons: ["overdue"], pending_submissions_count: 0, can_delete: true,
      }],
      total: (deletedDecision ? 0 : 1) + (deletedTask ? 0 : 1),
    },
  }));
  await page.route("**/api/v1/admin/decision-queue/decisions/701", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    deletedDecision = true;
    await route.fulfill({ json: { kind: "decision", id: 701, status: "dismissed", deleted: true, restored: false, reversible: true } });
  });
  await page.route("**/api/v1/admin/decision-queue/decisions/701/restore", async (route) => {
    deletedDecision = false;
    await route.fulfill({ json: { kind: "decision", id: 701, status: "open", deleted: false, restored: true, reversible: true } });
  });
  await page.route("**/api/v1/admin/decision-queue/tasks/801", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    deletedTask = true;
    await route.fulfill({ json: { kind: "task", id: 801, status: "cancelled", deleted: true, restored: false, reversible: true } });
  });

  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: /^Очередь решений/ }).click();
  await expect(page.getByText("Тестовая эскалация на удаление")).toBeVisible();
  await expect(page.getByText("Просроченное тестовое задание")).toBeVisible();

  await page.getByTestId("decision-queue-items").getByRole("button", { name: "Удалить" }).click();
  await expect(page.getByText("Удалить из очереди решений?")).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить удаление" }).click();
  await expect(page.getByText("Тестовая эскалация на удаление")).toHaveCount(1); // shown in undo banner
  await expect(page.getByTestId("decision-queue-items")).toHaveCount(0);

  await page.getByRole("button", { name: "Вернуть" }).click();
  await expect(page.getByTestId("decision-queue-items").getByText("Тестовая эскалация на удаление")).toBeVisible();

  await page.getByTestId("decision-queue-tasks").getByRole("button", { name: "Удалить" }).click();
  await page.getByRole("button", { name: "Подтвердить удаление" }).click();
  await expect(page.getByTestId("decision-queue-tasks")).toHaveCount(0);
});

test("Решить сегодня opens event and project resolvers, not section menus", async ({ page }) => {
  await page.route("**/api/v1/admin/dashboard", (route) => route.fulfill({
    json: {
      metrics: {
        current_roster: 10,
        events_pending: 2,
        activity_results: 3,
        projects_review: 1,
        event_waitlist: 4,
      },
      attention_total: 10,
    },
  }));
  await page.route("**/api/v1/admin/events", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/admin/projects", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/admin/activities/submissions**", (route) => route.fulfill({ json: [] }));
  await enterAdminWorkspace(page);

  await openMoreTools(page);
  await page.getByRole("button", { name: /2 · События на согласовании/ }).click();
  await expect(page.getByRole("heading", { name: "На согласовании" })).toBeVisible();
  await expect(page.getByText("Создать мероприятие", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Обзор", exact: true }).click();
  await openMoreTools(page);
  await page.getByRole("button", { name: /4 · лист ожидания/ }).click();
  await expect(page.getByRole("heading", { name: "Участники и посещаемость" })).toBeVisible();
  await expect(page.getByText("Создать мероприятие", { exact: true })).toHaveCount(0);
  await expect(page.getByText("На согласовании", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Обзор", exact: true }).click();
  await openMoreTools(page);
  await page.getByRole("button", { name: /3 · Результаты активностей/ }).click();
  await expect(page.getByRole("heading", { name: "Активности после события" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Проверить результаты/ })).toHaveCount(0);
  await expect(page.getByText("Активностей на проверке нет.")).toBeVisible();

  await page.getByRole("button", { name: "Обзор", exact: true }).click();
  await openMoreTools(page);
  await page.getByRole("button", { name: /1 · Проекты на проверке/ }).click();
  await expect(page.getByRole("heading", { name: "Проекты на рассмотрении" })).toBeVisible();
  await expect(page.getByText("Создать проект", { exact: true })).toHaveCount(0);
});

test("appoint-leader deep link opens the packages screen", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}&eraPath=admin&adminSection=appoint-leader`);
  await expect(page.getByRole("heading", { level: 2, name: "Назначить руководителя" })).toBeVisible();
  await expect(page.getByText("Пакеты функций", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Назначить и открыть функции" })).toBeDisabled();
});

test("appoint leader keeps selected person after search clears", async ({ page }) => {
  await page.route("**/api/v1/admin/offices**", async (route) => {
    const url = route.request().url();
    if (url.includes("assignable-users")) {
      await route.fulfill({
        json: [{
          id: 42,
          telegram_id: 4242,
          first_name: "Activist",
          last_name: "Candidate",
          username: "act_cand",
          role: "activist",
          application_status: "approved",
          is_blocked: false,
          is_archived: false,
        }],
      });
      return;
    }
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [] });
      return;
    }
    await route.continue();
  });
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди", exact: true }).click();
  await page.getByRole("button", { name: /Назначить руководителя/ }).click();
  await page.getByPlaceholder("Имя или @username").fill("Activist");
  await page.getByRole("button", { name: /Activist Candidate/ }).click();
  await page.getByPlaceholder("Имя или @username").fill("");
  await expect(page.getByText(/Выбран:.*Activist Candidate/)).toBeVisible();
  await expect(page.getByText(/activist/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Назначить и открыть функции" })).toBeEnabled();
});

test("analytics expands from overview instead of a separate control hub", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: /Аналитика/ }).click();

  await expect(page.getByRole("heading", { name: "ЭРА одним взглядом" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Главное" })).toBeVisible();
  for (const name of ["Обзор", "Люди", "Деятельность", "Команда", "Возможности", "Отчёты"]) {
    await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
  }
  await expect(page.getByText("Публикации канала", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Люди", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Все показатели" })).toBeVisible();
  const engagement = page.locator("details.analytics-metric-group").filter({ has: page.locator("summary", { hasText: /Вовлечённость.*показателей/ }) });
  await engagement.locator("summary").click();
  await expect(engagement.getByText("Числитель:", { exact: false }).first()).toBeVisible();
});

test("analytics sends the selected report through the authenticated bot delivery endpoint", async ({ page }) => {
  await page.route("**/api/v1/admin/analytics/executive-report/send", route => route.fulfill({ json: { sent: true } }));
  await enterAdminWorkspace(page);
  await openMoreTools(page);
  await page.getByRole("button", { name: /Аналитика/ }).click();
  const requestPromise = page.waitForRequest(request => request.method() === "POST" && request.url().endsWith("/executive-report/send"));
  await page.getByRole("button", { name: "PDF в чат с ботом", exact: true }).click();
  const request = await requestPromise;
  const body = request.postDataJSON();
  expect(body.format).toBe("pdf");
  expect(body.period).toBe("custom");
  expect(body.request_key.length).toBeGreaterThanOrEqual(16);
  expect(body.chat_id).toBeUndefined();
  await expect(page.getByRole("status", { name: "Готово: Отчёт отправлен в личный чат с ботом ЭРА.", exact: true })).toBeVisible();
});

test("analytics exports selected custom period as a complete PDF", async ({ page }) => {
  await enterAdminWorkspace(page);
  await openMoreTools(page);
  await page.getByRole("button", { name: /Аналитика/ }).click();
  await page.getByLabel("Период отчёта").selectOption("custom");
  const downloadButton = page.getByRole("button", { name: "↓ Скачать отчёт PDF" });
  await expect(downloadButton).toBeDisabled();
  await page.getByLabel("Начало периода").fill("2026-01-01");
  await page.getByLabel("Конец периода").fill("2026-10-21");
  const responsePromise = page.waitForResponse((response) =>
    response.request().method() === "GET" && response.url().includes("executive-report.pdf"));
  const downloadPromise = page.waitForEvent("download");
  await downloadButton.click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("application/pdf");
  expect(response.url()).toContain("start_date=2026-01-01");
  expect(response.url()).toContain("end_date=2026-10-21");
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("ERA_analytics_2026-01-01_2026-10-21.pdf");
  const path = await download.path();
  expect(path).not.toBeNull();
  const pdf = await readFile(path!);
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  expect(pdf.length).toBeGreaterThan(10_000);
  await expect(downloadButton).toBeEnabled();
  for (const width of [320, 430, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const heading = await page.getByRole("heading", { name: "ЭРА одним взглядом" }).boundingBox();
    expect(heading?.width).toBeGreaterThan(200);
  }
});

test("analytics quick action opens the actual tasks workspace", async ({ page }) => {
  await enterAdminWorkspace(page);
  await openMoreTools(page);
  await page.getByRole("button", { name: /Аналитика/ }).click();
  await page.getByRole("button", { name: "Открыть задания →", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Дать работу или проверить результат" })).toBeVisible();
});

test("analytics shows observed zero counters and excludes personal-list shortcuts", async ({ page }) => {
  await page.route('**/api/v1/admin/analytics/v2?*', async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.sources = payload.sources.map((source: { id: string }) => ({ ...source, started_at: '2026-10-21T22:10:00Z',
      observed_value: 0, value: null, data_state: 'insufficient', connection_status: 'collecting',
      rolling_counts: [7,30,90].map((days) => ({ days, observed: 0, complete: false })) }));
    await route.fulfill({ response, json: payload });
  });
  await enterAdminWorkspace(page);
  await openMoreTools(page);
  await page.getByRole("button", { name: /Аналитика/ }).click();
  await expect(page.getByLabel("Период отчёта")).toHaveValue("month");
  const source = page.locator('.era-card').filter({ has: page.getByRole('heading', { name: 'Публикации канала', exact: true }) });
  await expect(source.locator('.analytics-number')).toHaveText('0');
  await expect(source).toContainText('Фактически учтено');
  await expect(source).toContainText('7 дней');
  await page.getByRole('tab', { name: 'Люди', exact: true }).click();
  await expect(page.getByText('Только сводные числа.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: /Все профили в базе/ })).toHaveCount(0);
});

test("overview KPI opens exact underlying rows", async ({ page }) => {
  await enterAdminWorkspace(page);

  const currentRoster = page.getByRole("button", { name: /Участники.*Открыть состав/ });
  await expect(currentRoster).toBeVisible();
  await currentRoster.click();

  await expect(page.getByRole("heading", { name: "Текущий состав" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Скачать эти .* строк.* в Excel/ })).toBeVisible();
});

test("leaders workcenter creates a task and confirms a separate leader status", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди", exact: true }).click();
  await page.getByRole("button", { name: /Лидеры.*Команда, задачи, рассылки и Пульс/ }).click();
  for (const name of ["Команда", "Задачи", "Рассылки", "Пульс"]) {
    await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "➕ Новая задача", exact: true }).click();
  const title = `E2E поручение ${Date.now()}`;
  await page.getByLabel("Что сделать", { exact: true }).fill(title);
  await expect(page.getByLabel("Зачем и какой результат нужен")).not.toBeVisible();
  await page.getByText("Дополнительно: описание, направление, баллы", { exact: true }).click();
  await page.getByLabel("Зачем и какой результат нужен").fill("Проверить общий процесс");
  await page.getByRole("button", { name: "Предпросмотр", exact: true }).click();
  await page.getByRole("button", { name: "Создать задачу", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Задача сохранена");
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Команда", exact: true }).click();
  await page.getByLabel("Поиск участника").fill("E2E Participant");
  await page.getByRole("button", { name: "Найти / назначить лидера", exact: true }).click();
  await page.getByRole("button", { name: "Назначить лидером", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Подтвердите изменение" })).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Статус обновлён");
  await expect(page.getByRole("button", { name: "Снять статус лидера", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Снять статус лидера", exact: true }).click();
  await page.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(page.getByRole("button", { name: "Назначить лидером", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Рассылки", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Сообщение команде" })).toBeVisible();
});

test("admin can remove an open task in Работа → Задания with confirmation and undo", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Работа", exact: true }).click();
  await page.getByRole("button", { name: /Задания.*Создание задач/ }).click();
  await page.getByRole("button", { name: /Создать задание/ }).click();

  await page.getByRole("button", { name: "Новая открытая задача" }).click();
  const taskTitle = `E2E убрать задачу ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(taskTitle);
  await page.getByPlaceholder("Описание").fill("Временная тестовая задача для проверки удаления.");
  const futureDeadline = new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16);
  await page.locator('input[type="datetime-local"]').fill(futureDeadline);
  await page.getByRole("button", { name: "Опубликовать" }).click();

  const card = page
    .locator(".era-card")
    .filter({ hasText: taskTitle })
    .filter({ has: page.getByRole("button", { name: "Убрать", exact: true }) });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Убрать", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Убрать задачу?" })).toBeVisible();
  await page.getByPlaceholder("Причина (необязательно)").fill("Неактуально");
  await page.getByRole("button", { name: "Убрать задачу", exact: true }).click();

  await expect(card).toHaveCount(0);
  await expect(page.getByText("Задача убрана", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Вернуть", exact: true }).click();
  await expect(card).toBeVisible();
});
