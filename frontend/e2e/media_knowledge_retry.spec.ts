import { expect, test } from "@playwright/test";

test("media knowledge retries read errors without exposing stale library entries", async ({ page }) => {
  let reads = 0;
  let writes = 0;
  page.on("request", request => {
    if (request.url().includes("/api/v1/media/library") && request.method() !== "GET") writes += 1;
  });
  await page.route("**/api/v1/media/library**", route => {
    reads += 1;
    if (reads === 1 || reads === 3) {
      return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"temporary"}' });
    }
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify([{
        id: 900011, title: "Проверочный материал", description: "Только браузерный mock",
        category: "guides", kind: "text", url: "", pinned: false,
        is_active: true, revision: 1,
      }]),
    });
  });

  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /База знаний.*Инструкции, шаблоны/ }).click();
  await expect(page.getByRole("button", { name: "Повторить загрузку базы знаний" })).toBeVisible();
  await expect(page.getByText("Проверочный материал", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Повторить загрузку базы знаний" }).click();
  await expect(page.getByText("Проверочный материал", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Обновить базу знаний" }).click();
  await expect(page.getByRole("button", { name: "Повторить загрузку базы знаний" })).toBeVisible();
  await expect(page.getByText("Проверочный материал", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Повторить загрузку базы знаний" }).click();
  await expect(page.getByText("Проверочный материал", { exact: true })).toBeVisible();
  expect(reads).toBe(4);
  expect(writes).toBe(0);
});
