import { expect, test, type Page } from "@playwright/test";

const event = {
  id: 669,
  title: "12 декабря для ЭРА — особенная дата.",
  event_date: "2026-12-12",
  event_time: "18:00",
  location: "Дом Москвы в Ереване",
  display_status: "Регистрация открыта",
  participant_limit: null,
  remaining_count: null,
  points_for_visit: 0,
  anniversary_registration_open: true,
  anniversary_registered: false,
  anniversary_defaults: { first_name: "Анна", last_name: "Иванова", organization: "ЭРА" },
  program: [],
  participant_tasks: [],
  status: "published",
  can_register: true,
  registration_status: null,
  waitlist_enabled: false,
  registration_required: true,
  short_description: null,
  full_description: null,
  description: "",
  end_time: null,
  address: null,
  format: "offline",
  attendance_mode: "in_person",
  category: null,
  organizer: null,
  participant_value: null,
  contact: null,
  chat_url: null,
  project_id: null,
  available_places: "",
  poster_url: null,
};

async function mockAnniversary(page: Page, organization: string | null) {
  let registered = false;
  const requests: unknown[] = [];
  const snapshot = () => ({
    ...event,
    display_status: registered ? "Вы зарегистрированы" : event.display_status,
    anniversary_registered: registered,
    anniversary_defaults: { ...event.anniversary_defaults, organization },
  });
  await page.route("**/api/v1/miniapp/auth", (route) => route.fulfill({ json: {
    token: "isolated-test",
    expires_at: "2099-01-01T00:00:00Z",
    user: { id: 1, telegram_id: 900001, first_name: "Анна", application_status: "approved",
      role: "participant", is_blocked: false, is_admin: false, is_leader: false, features: {} },
  } }));
  await page.route("**/api/v1/home", (route) => route.fulfill({ json: {
    featured_event: snapshot(),
    growth: { label: "Участник" },
    activity: { completed_tasks: 0 },
    opportunities: [],
  } }));
  await page.route("**/api/v1/home/daily-quote", (route) => route.fulfill({ json: { text: "" } }));
  await page.route("**/api/v1/events?*", (route) => route.fulfill({ json: [snapshot()] }));
  await page.route("**/api/v1/events/669/anniversary-rsvp", (route) => {
    requests.push(route.request().postDataJSON());
    registered = true;
    return route.fulfill({ json: snapshot() });
  });
  return requests;
}

test("orbit card opens detail where anniversary registers in one click", async ({ page }) => {
  const requests = await mockAnniversary(page, "ЭРА");
  await page.goto("/app/?devTelegramId=900001");
  await page.getByRole("region", { name: "Ближайшее" }).getByRole("button", { name: new RegExp(event.title) }).click();
  await expect(page.getByRole("heading", { name: event.title })).toBeVisible();
  await page.getByRole("button", { name: "Зарегистрироваться", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Вы зарегистрированы" })).toBeVisible();
  expect(requests).toEqual([{}]);
  // Reload keeps the detail hash; status must survive without re-opening from home.
  await page.reload();
  await expect(page.getByRole("heading", { name: event.title })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Вы зарегистрированы" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Зарегистрироваться", exact: true })).toHaveCount(0);
});

test("the participation card opens the short form when the profile lacks an organization", async ({ page }) => {
  const requests = await mockAnniversary(page, null);
  await page.goto("/app/?devTelegramId=900001#/events");
  await page.getByRole("button", { name: new RegExp(event.title) }).first().click();
  await page.getByRole("button", { name: "Зарегистрироваться", exact: true }).click();
  const form = page.getByRole("dialog", { name: "Регистрация на годовщину" });
  await expect(form.getByLabel("Имя", { exact: true })).toHaveValue("Анна");
  await expect(form.getByLabel("Фамилия")).toHaveValue("Иванова");
  expect(requests).toEqual([]);
  await form.getByLabel("Организация").fill("Без организации");
  await form.getByRole("button", { name: "Подтвердить" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Вы зарегистрированы" })).toBeVisible();
  expect(requests).toEqual([{ first_name: "Анна", last_name: "Иванова", organization: "Без организации" }]);
});

test("an existing anniversary participant can still open cancellation", async ({ page }) => {
  await mockAnniversary(page, "ЭРА");
  await page.route("**/api/v1/events?*", (route) => route.fulfill({ json: [{
    ...event,
    display_status: "Вы зарегистрированы",
    registration_status: "registered",
    anniversary_registered: true,
    program: [],
    participant_tasks: [],
  }] }));
  await page.route("**/api/v1/events/669/**", (route) => route.fulfill({ json: [] }));
  await page.goto("/app/?devTelegramId=900001#/events/669");
  await page.getByRole("button", { name: "Отказаться", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Отказаться от участия?" })).toBeVisible();
});
