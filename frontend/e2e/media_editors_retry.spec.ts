import { expect, test } from "@playwright/test";

test("media calendar editors retry GET without stale privileged controls or writes", async ({ page }) => {
  let reads = 0;
  let writes = 0;
  page.on("request", request => {
    if (request.url().includes("/api/v1/media/workspaces/era/editors") && request.method() !== "GET") writes += 1;
  });
  await page.route("**/api/v1/media/workspaces", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: "era", title: "ЭРА", platforms: {}, topic_url: "",
      can_manage: true, can_assign_editors: true }]),
  }));
  await page.route("**/api/v1/media/workspaces/era/calendar?**", route =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/media/workspaces/era/team", route =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/media/workspaces/era/editors", route => {
    reads += 1;
    if (reads === 1 || reads === 3) {
      return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"temporary"}' });
    }
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ revision: reads, editors: reads === 2
        ? [{ id: 900011, name: "Тестовый редактор" }] : [] }),
    });
  });

  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /^ЭРА →/ }).click();
  await page.getByRole("button", { name: "Редакторы календаря" }).click();

  await expect(page.getByRole("button", { name: "Повторить загрузку редакторов" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Снять доступ: Тестовый редактор" })).toHaveCount(0);
  await page.getByRole("button", { name: "Повторить загрузку редакторов" }).click();
  await expect(page.getByRole("button", { name: "Снять доступ: Тестовый редактор" })).toBeVisible();

  await page.getByRole("button", { name: "Обновить список редакторов" }).click();
  await expect(page.getByRole("button", { name: "Повторить загрузку редакторов" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Снять доступ: Тестовый редактор" })).toHaveCount(0);

  await page.getByRole("button", { name: "Повторить загрузку редакторов" }).click();
  await expect(page.getByText("Редакторы пока не назначены.")).toBeVisible();
  expect(reads).toBe(4);
  expect(writes).toBe(0);
});
