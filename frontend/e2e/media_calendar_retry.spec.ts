import { expect, test } from "@playwright/test";

test("media calendar retries GET failures without retaining stale editor controls", async ({ page }) => {
  let reads = 0;
  let writes = 0;
  page.on("request", request => {
    if (request.url().includes("/api/v1/media/workspaces/") && request.method() !== "GET") writes += 1;
  });
  await page.route("**/api/v1/media/workspaces", route => {
    reads += 1;
    if (reads === 1 || reads === 3) {
      return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"temporary"}' });
    }
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify([{
        id: "era", title: "ЭРА", platforms: {}, topic_url: "",
        can_manage: reads === 2, can_assign_editors: reads === 2,
      }]),
    });
  });
  await page.route("**/api/v1/media/workspaces/era/calendar?**", route =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/media/workspaces/era/team", route =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));

  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /^ЭРА →/ }).click();
  await expect(page.getByRole("button", { name: "Повторить загрузку календаря" })).toBeVisible();
  await expect(page.getByRole("button", { name: "+ Добавить материал" })).toHaveCount(0);

  await page.getByRole("button", { name: "Повторить загрузку календаря" }).click();
  await expect(page.getByRole("button", { name: "+ Добавить материал" })).toBeVisible();
  await page.getByLabel("Показать", { exact: true }).selectOption("published");
  await expect(page.getByRole("button", { name: "Повторить загрузку календаря" })).toBeVisible();
  await expect(page.getByRole("button", { name: "+ Добавить материал" })).toHaveCount(0);

  await page.getByRole("button", { name: "Повторить загрузку календаря" }).click();
  await expect(page.getByRole("button", { name: "Обновить календарь" })).toBeVisible();
  await expect(page.getByRole("button", { name: "+ Добавить материал" })).toHaveCount(0);
  expect(reads).toBe(4);
  expect(writes).toBe(0);
});
