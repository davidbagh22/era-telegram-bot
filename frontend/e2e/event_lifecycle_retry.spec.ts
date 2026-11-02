import { expect, test } from "@playwright/test";

// All event and attendance reads are intercepted in the disposable browser.
// Retrying the lifecycle card must never start, complete or close a real event.
test("admin retries a failed lifecycle read and refreshes status without writes", async ({ page }) => {
  let reads = 0;
  let writes = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/admin/events/4243/") && request.method() !== "GET") {
      writes += 1;
    }
  });

  await page.route("**/api/v1/admin/events/operational", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([{
      id: 4243, title: "E2E состояние мероприятия", status: "published",
      event_date: "2026-11-07", event_time: "18:00", location: "Тестовый зал",
      registered: 0, free: 10, points_for_visit: 150,
    }]),
  }));
  await page.route("**/api/v1/admin/events/4243/participants", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: "[]",
  }));
  await page.route("**/api/v1/admin/events/4243/attendance-state", (route) => {
    reads += 1;
    if (reads === 1) {
      return route.fulfill({
        status: 503, contentType: "application/json",
        body: JSON.stringify({ detail: "temporary outage" }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        event_id: 4243, status: "published",
        started_at: reads === 2 ? null : "2026-11-07T14:00:00Z",
        completed_at: reads === 2 ? null : "2026-11-07T16:00:00Z",
        attendance_code: null, can_start: false, can_complete: false,
        confirmation_open: false, confirmation_closed_at: null, notified_count: 0,
      }),
    });
  });

  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();
  await page.getByText("E2E состояние мероприятия").click();

  await expect(page.getByText("Не удалось загрузить управление мероприятием.")).toBeVisible();
  await page.getByRole("button", { name: "Повторить загрузку управления" }).click();
  await expect(page.getByText("ГОТОВО К СТАРТУ")).toBeVisible();
  await page.getByRole("button", { name: "Обновить управление" }).click();
  await expect(page.getByText("ЗАВЕРШЕНО")).toBeVisible();
  expect(reads).toBe(3);
  expect(writes).toBe(0);
});
