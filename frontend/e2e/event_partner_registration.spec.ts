import { expect, test } from "@playwright/test";
import type { EventItem } from "../src/types/activity";

const partnerEvent: EventItem = {
  id: 88,
  title: "Географический диктант — 2026",
  description: "Ежегодная международная просветительская акция",
  short_description: "Ежегодная международная просветительская акция",
  full_description: "Проверим географические знания.",
  event_date: "2026-11-22", event_time: "12:00", end_time: null,
  location: "Русский дом, Ереван", address: null,
  format: "Офлайн", attendance_mode: "offline",
  category: "Просветительская акция", organizer: null, participant_value: null,
  contact: null, chat_url: "https://t.me/c/2973371133/27001",
  registration_url: "https://t.me/+quri_BnuHaxjZTVi",
  points_for_visit: 0, project_id: null,
  status: "published", display_status: "Регистрация по ссылке",
  participant_limit: null, registered_count: 0,
  available_places: "Без ограничения мест", remaining_count: null,
  registration_status: null, waitlist_enabled: false,
  registration_required: false, registration_close_at: null,
  can_register: false, program: [], participant_tasks: [],
  poster_url: null,
};

test("partner event in Mini App uses the external registration CTA", async ({ page }) => {
  await page.route((url) => url.pathname === "/api/v1/events" && url.searchParams.has("scope"), route =>
    route.fulfill({ json: [partnerEvent] }));
  await page.goto("/app/?devTelegramId=900001#/events/88");
  await expect(page.getByRole("heading", { name: "Географический диктант — 2026" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Записаться по ссылке/ })).toHaveAttribute(
    "href", "https://t.me/+quri_BnuHaxjZTVi",
  );
  await expect(page.getByRole("button", { name: "Подтвердить регистрацию" })).toHaveCount(0);
  await expect(page.getByText("Регистрация по ссылке")).toBeVisible();
});
