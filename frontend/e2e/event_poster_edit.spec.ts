import { expect, test } from "@playwright/test";

const POSTER = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6ZAAAAABJRU5ErkJggg==",
  "base64",
);

test("manager replaces a published poster without republishing or touching registrations", async ({ page }) => {
  let uploads = 0;
  let removals = 0;
  let publications = 0;
  await page.route("**/api/v1/admin/events/operational", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{
      id: 4242, title: "E2E опубликованная афиша", status: "published",
      event_date: "2026-11-07", event_time: "18:00", location: "Дом Москвы",
      registered: 3, free: 12, points_for_visit: 150,
    }]),
  }));
  await page.route("**/api/v1/admin/events/4242/draft", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ id: 4242, title: "E2E опубликованная афиша", status: "published", has_poster: true }),
  }));
  await page.route("**/api/v1/admin/events/4242/poster/preview", (route) => route.fulfill({
    status: 200, contentType: "image/png", body: POSTER,
  }));
  await page.route("**/api/v1/admin/events/4242/poster", (route) => {
    uploads += 1;
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ id: 4242, title: "E2E опубликованная афиша", status: "published", has_poster: true }),
    });
  });
  await page.route("**/api/v1/admin/events/4242/poster/remove", (route) => {
    removals += 1;
    return route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ id: 4242, title: "E2E опубликованная афиша", status: "published", has_poster: false }) });
  });
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/publish")) publications += 1;
  });

  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();
  await page.getByRole("button", { name: "Изменить афишу" }).click();

  await expect(page.getByRole("heading", { name: "Редактировать афишу" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Текущая афиша" })).toBeVisible();
  const input = page.getByLabel("Выбрать изображение афиши");
  await input.setInputFiles({ name: "bad.txt", mimeType: "text/plain", buffer: Buffer.from("not an image") });
  await expect(page.getByRole("alert")).toContainText("JPG, PNG или WEBP");
  expect(uploads).toBe(0);

  await input.setInputFiles({ name: "poster.png", mimeType: "image/png", buffer: POSTER });
  await expect(page.getByRole("status")).toContainText("Афиша обновлена");
  await expect(page.getByRole("img", { name: "Текущая афиша" })).toBeVisible();
  expect(uploads).toBe(1);
  expect(publications).toBe(0);

  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Удалить только изображение" }).click();
  expect(removals).toBe(0);
  await page.getByRole("button", { name: "← К списку мероприятий" }).click();
  await expect(page.getByText("E2E опубликованная афиша")).toBeVisible();
});
