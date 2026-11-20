import { expect, test } from "@playwright/test";
import type { EventItem } from "../src/types/activity";

const geo: EventItem = {
  id: 76, title: "Географический диктант — 2026",
  description: "Международная просветительская акция",
  short_description: "Международная просветительская акция",
  full_description: "Международная просветительская акция",
  event_date: "2026-11-22", event_time: "12:00", end_time: null,
  location: "Русский дом", address: null, format: "Офлайн",
  attendance_mode: "offline", category: null, organizer: null,
  participant_value: null, contact: "https://t.me/+quri_BnuHaxjZTVi",
  chat_url: "https://t.me/c/123/456", points_for_visit: 0,
  project_id: null, status: "registration_open",
  display_status: "Запись по ссылке организаторов",
  participant_limit: null, registered_count: 0,
  available_places: "Без ограничения мест", remaining_count: null,
  registration_status: null, waitlist_enabled: false,
  registration_required: false, registration_close_at: null,
  can_register: false, program: [], participant_tasks: [],
  poster_url: null, signup_defaults: null,
};

test("external geography event displays a real signup CTA and no ERA registration form", async ({ page }) => {
  await page.route((url) => url.pathname === "/api/v1/events" && url.searchParams.has("scope"),
    async route => { await route.fulfill({ json: [geo] }); });
  await page.goto("/app/?devTelegramId=900001#/events/76");
  await expect(page.getByRole("heading", { name: "Географический диктант — 2026" })).toBeVisible();
  const signup = page.getByRole("link", { name: /Записаться по ссылке/ });
  await expect(signup).toBeVisible();
  await expect(signup).toHaveAttribute("href", "https://t.me/+quri_BnuHaxjZTVi");
  await expect(page.getByRole("button", { name: "Регистрация не нужна" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Подтвердить регистрацию" })).toHaveCount(0);
});
