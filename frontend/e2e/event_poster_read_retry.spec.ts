import { expect, test } from "@playwright/test";

const POSTER = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6ZAAAAABJRU5ErkJggg==",
  "base64",
);

// Disposable browser mocks every event endpoint: retries must remain read-only.
test("published poster editor recovers from draft and image GET failures", async ({ page }) => {
  let draftReads = 0;
  let previewReads = 0;
  let eventWrites = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/admin/events/4244/") && request.method() !== "GET") {
      eventWrites += 1;
    }
  });

  await page.route("**/api/v1/admin/events/operational", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{
      id: 4244, title: "E2E афиша с ошибкой сети", status: "published",
      event_date: "2026-11-07", event_time: "18:00", location: "Тестовый зал",
      registered: 0, free: 10, points_for_visit: 150,
    }]),
  }));
  await page.route("**/api/v1/admin/events/4244/draft", (route) => {
    draftReads += 1;
    if (draftReads === 1) {
      return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"temporary"}' });
    }
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ id: 4244, title: "E2E афиша с ошибкой сети", status: "published", has_poster: true }),
    });
  });
  await page.route("**/api/v1/admin/events/4244/poster/preview", (route) => {
    previewReads += 1;
    if (previewReads === 1) {
      return route.fulfill({ status: 503, contentType: "application/json", body: "unavailable" });
    }
    return route.fulfill({ status: 200, contentType: "image/png", body: POSTER });
  });

  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();
  await page.getByRole("button", { name: "Изменить афишу" }).click();

  await expect(page.getByRole("alert")).toContainText("Не удалось открыть мероприятие");
  await page.getByRole("button", { name: "Повторить загрузку мероприятия" }).click();
  await expect(page.getByRole("heading", { name: "Редактировать афишу" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Не удалось загрузить изображение афиши");
  await expect(page.getByText("Загружаем изображение…")).toHaveCount(0);
  await page.getByRole("button", { name: "Повторить загрузку изображения" }).click();
  await expect(page.getByRole("img", { name: "Текущая афиша" })).toBeVisible();
  expect(draftReads).toBe(2);
  expect(previewReads).toBe(2);
  expect(eventWrites).toBe(0);
});
