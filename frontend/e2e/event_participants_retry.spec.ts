import { expect, test } from "@playwright/test";

// Disposable browser mocks all event/participant reads. Never creates or alters
// real events, registrations, attendance, points, or Telegram deliveries.
test("admin can retry failed participant list and refresh it without writes", async ({ page }) => {
  let reads = 0;
  let writes = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/admin/events/4243/participants") && request.method() !== "GET") {
      writes += 1;
    }
  });
  await page.route("**/api/v1/admin/events/operational", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([{
      id: 4243, title: "E2E список участников", status: "published",
      event_date: "2026-11-07", event_time: "18:00", location: "Тестовый зал",
      registered: 1, free: 9, points_for_visit: 150,
    }]),
  }));
  await page.route("**/api/v1/admin/events/4243/participants", (route) => {
    reads += 1;
    if (reads === 1) {
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "temporary outage" }) });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(reads === 2 ? [] : [{
        registration_id: 31, participant_id: 42,
        participant_name: "E2E Участник", status: "registered",
      }]),
    });
  });

  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();
  await page.getByText("E2E список участников").click();

  await expect(page.getByText("Не удалось загрузить участников.")).toBeVisible();
  await page.getByRole("button", { name: "Повторить загрузку участников" }).click();
  await expect(page.getByText("Пока никто не зарегистрирован. Как только появится первая регистрация, участник будет здесь.")).toBeVisible();
  await page.getByRole("button", { name: "Обновить участников" }).click();
  await expect(page.getByText("E2E Участник")).toBeVisible();
  expect(reads).toBe(3);
  expect(writes).toBe(0);
});
