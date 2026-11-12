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


test("corrupt media revision stays visible but cannot be edited or published", async ({ page }) => {
  let writes = 0;
  page.on("request", request => {
    if (request.url().includes("/api/v1/media/workspaces/") && request.method() !== "GET") writes += 1;
  });
  await page.route("**/api/v1/media/workspaces", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: "era", title: "ЭРА", platforms: {}, topic_url: "", can_manage: true, can_assign_editors: false }]),
  }));
  await page.route("**/api/v1/media/workspaces/era/calendar?**", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{
      id: 42, area: "era", title: "Повреждённый материал", body: "Сохранённая запись",
      platform: "unknown", status: "planned", scheduled_at: null,
      responsible_id: null, materials: "", publication_url: null,
      publication_evidence: null, revision: null,
    }]),
  }));
  await page.route("**/api/v1/media/workspaces/era/team", route => route.fulfill({
    status: 200, contentType: "application/json", body: "[]",
  }));
  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /^ЭРА →/ }).click();
  await expect(page.getByText("Повреждённый материал", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Открыть материал" }).click();
  await expect(page.getByText(/Редактирование отключено до проверки администратором/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Изменить материал / ответственного" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "На согласование" })).toHaveCount(0);
  expect(writes).toBe(0);
});
