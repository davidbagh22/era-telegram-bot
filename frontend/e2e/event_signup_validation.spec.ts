import { expect, test } from "@playwright/test";
import type { EventItem } from "../src/types/activity";

const event: EventItem = {
  id: 31, title: "Тайны Серебряного века",
  description: "Творческий вечер", short_description: "Творческий вечер",
  full_description: "Творческий вечер", event_date: "2026-11-24",
  event_time: "19:00", end_time: null,
  location: "Дом Москвы", address: null, format: "Офлайн",
  attendance_mode: "offline", category: null, organizer: null,
  participant_value: null, contact: null, chat_url: null,
  points_for_visit: 0, project_id: null,
  status: "registration_open", display_status: "Регистрация открыта",
  participant_limit: null, registered_count: 0,
  available_places: "Без ограничения мест", remaining_count: null,
  registration_status: null, waitlist_enabled: false,
  registration_required: true, registration_close_at: null,
  can_register: true, program: [], participant_tasks: [],
  poster_url: null,
  signup_defaults: {
    full_name: "Багдасарян Давид",
    organization: "РЭУ",
    phone: "+37477566005",
  },
};

test("event signup checks patronymic before submit and renders structured 422 without [object Object]", async ({ page }) => {
  await page.route((url) => url.pathname === "/api/v1/events" && url.searchParams.has("scope"), async route => {
    await route.fulfill({ json: [event] });
  });
  let posts = 0;
  await page.route("**/api/v1/events/31/register", async route => {
    posts += 1;
    await route.fulfill({
      status: 422,
      json: { detail: [{ type: "string_pattern_mismatch", loc: ["body", "full_name"], msg: "String should match pattern" }] },
    });
  });
  await page.goto("/app/?devTelegramId=900001#/events/31");
  await expect(page.getByRole("heading", { name: "Тайны Серебряного века" })).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить регистрацию" }).click();
  await expect(page.getByRole("alert").first()).toContainText("Добавьте отчество");
  expect(posts).toBe(0);

  await page.getByLabel("Фамилия, имя и отчество").fill("Багдасарян Давид Саргисович");
  await page.getByRole("button", { name: "Подтвердить регистрацию" }).click();
  await expect(page.getByText(/Укажите фамилию, имя и отчество полностью/).first()).toBeVisible();
  await expect(page.getByText("[object Object]")).toHaveCount(0);
  expect(posts).toBe(1);
});
