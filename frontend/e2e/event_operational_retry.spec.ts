import { expect, test } from "@playwright/test";

// All responses are intercepted inside the disposable Playwright browser.
// No production events, registrations, publications or Telegram messages are created.
test("admin can retry a failed operational event list and refresh its actual contents", async ({ page }) => {
  let reads = 0;
  let writes = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/admin/events/operational") && request.method() !== "GET") {
      writes += 1;
    }
  });
  await page.route("**/api/v1/admin/events/operational", (route) => {
    reads += 1;
    if (reads === 1) {
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "temporary outage" }) });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(reads === 2 ? [{
        id: 4243, title: "E2E актуальное мероприятие", status: "published",
        event_date: "2026-11-07", event_time: "18:00", location: "Тестовый зал",
        registered: 3, free: 12, points_for_visit: 150,
      }] : []),
    });
  });

  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();

  await expect(page.getByText("Не удалось загрузить мероприятия.")).toBeVisible();
  await page.getByRole("button", { name: "Повторить загрузку" }).click();
  await expect(page.getByText("E2E актуальное мероприятие")).toBeVisible();
  await expect(page.getByText("Записано: 3")).toBeVisible();

  await page.getByRole("button", { name: "Обновить список" }).click();
  await expect(page.getByText("Действующих мероприятий пока нет.")).toBeVisible();
  await expect(page.getByText("E2E актуальное мероприятие")).toHaveCount(0);
  expect(reads).toBe(3);
  expect(writes).toBe(0);
});
