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

test("a failed read after hiding a material clears stale cards and retries only the read", async ({ page }) => {
  let reads = 0;
  let writes = 0;
  const item = {
    id: 900012, title: "Материал для скрытия", description: "Только браузерный mock",
    category: "guides", kind: "text", url: "", pinned: false,
    is_active: true, revision: 1,
  };
  await page.route("**/api/v1/media/library**", route => {
    reads += 1;
    if (reads === 2) return route.fulfill({
      status: 503, contentType: "application/json", body: '{"detail":"temporary"}',
    });
    return route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify(reads === 1 ? [item] : []) });
  });
  await page.route("**/api/v1/media/desk/library/900012", route => {
    expect(route.request().method()).toBe("PATCH");
    expect(route.request().postDataJSON()).toEqual({ revision: 1, is_active: false });
    writes += 1;
    return route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ ...item, is_active: false, revision: 2 }) });
  });
  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /База знаний.*Инструкции, шаблоны/ }).click();
  await expect(page.getByText(item.title, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Скрыть материал", exact: true }).click();
  await expect(page.getByRole("button", { name: "Повторить загрузку базы знаний" })).toBeVisible();
  await expect(page.getByText(item.title, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Скрыть материал", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Повторить загрузку базы знаний" }).click();
  await expect(page.getByText("По этим условиям материалов пока нет.")).toBeVisible();
  expect(reads).toBe(3);
  expect(writes).toBe(1);
});
