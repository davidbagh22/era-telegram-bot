import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function eventCreator(page: Page) {
  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Создать мероприятие.*Черновик/ }).click();
}

test("quick event with photo restores its draft and publishes through preview", async ({ page }) => {
  await eventCreator(page);
  await page.getByRole("button", { name: "⚡ Быстро: текст и фото" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Текст анонса").fill("E2E быстрый анонс\nПолный текст встречи без сокращений.");
  await dialog.getByLabel("Дата", { exact: true }).fill("2026-11-07");
  await dialog.getByLabel("Время", { exact: true }).fill("18:00");
  await dialog.getByLabel("Место или ссылка").fill("Дом Москвы");
  await dialog.getByLabel("Фото (до 5 МБ)").setInputFiles({
    name: "poster.png", mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6ZAAAAABJRU5ErkJggg==", "base64"),
  });
  await expect(dialog.getByRole("img", { name: "Прикреплённая афиша" })).toBeVisible();
  await expect(dialog.getByText("Сохранено ✓", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Сохранить и закрыть" }).click();
  await expect(dialog).not.toBeVisible();
  await eventCreator(page);
  await page.getByRole("button", { name: /E2E быстрый анонс.*Быстрый ввод/ }).click();
  await expect(dialog.getByLabel("Текст анонса")).toHaveValue("E2E быстрый анонс\nПолный текст встречи без сокращений.");
  await expect(dialog.getByRole("img", { name: "Прикреплённая афиша" })).toBeVisible();
  await dialog.getByRole("button", { name: "Проверить публикацию" }).click();
  await expect(dialog.getByRole("img", { name: "Афиша мероприятия", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Опубликовать", exact: true }).click();
  await expect(dialog.getByRole("heading", { name: "Мероприятие опубликовано" })).toBeVisible();
  await dialog.getByRole("button", { name: "Готово", exact: true }).click();
  await page.getByRole("button", { name: "⚡ Быстро: текст и фото" }).click();
  await expect(dialog.getByLabel("Текст анонса")).toHaveValue("");
  await expect(dialog.getByRole("img")).toHaveCount(0);
});

test("lost publish response retries the same event instead of creating a duplicate", async ({ page }) => {
  await eventCreator(page);
  let creates = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/v1/admin/events/drafts")) creates += 1;
  });
  await page.getByRole("button", { name: "⚡ Быстро: текст и фото" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Текст анонса").fill("E2E повтор публикации\nПроверяем восстановление соединения.");
  await dialog.getByLabel("Место или ссылка").fill("Дом Москвы");
  await dialog.getByRole("button", { name: "Проверить публикацию" }).click();
  const publications: string[] = [];
  await page.route("**/api/v1/admin/events/*/publish", async (route) => {
    publications.push(route.request().url());
    const response = await route.fetch();
    if (publications.length === 1) await route.abort();
    else await route.fulfill({ response });
  });
  await expect(dialog.getByRole("button", { name: "Опубликовать", exact: true })).toBeEnabled();
  await dialog.getByRole("button", { name: "Опубликовать", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await dialog.getByRole("button", { name: "Опубликовать", exact: true }).click();
  await expect(dialog.getByRole("heading", { name: "Мероприятие опубликовано" })).toBeVisible();
  expect(creates).toBe(1);
  expect(publications).toHaveLength(2);
  expect(publications[0]).toBe(publications[1]);
});
