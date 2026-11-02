import { expect, test } from "@playwright/test";

const mediaHub = (canManage: boolean) => ({
  access_level: canManage ? "admin" : "no_access",
  permissions: {
    tools_read: canManage, content_plan_read: canManage, content_plan_write: canManage,
    members_manage: canManage, analytics_read: canManage, publications_manage: canManage,
  },
  chat_url: "", channel_url: "", open_tasks: [], my_tasks: [], can_manage: canManage,
});

test("media hub GET failure can be retried without joining or sending", async ({ page }) => {
  let reads = 0;
  let mediaWrites = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/media/") && request.method() !== "GET") mediaWrites += 1;
  });
  await page.route("**/api/v1/media/hub", (route) => {
    reads += 1;
    return route.fulfill({
      status: reads === 1 ? 503 : 200,
      contentType: "application/json",
      body: JSON.stringify(reads === 1 ? { detail: "temporary" } : mediaHub(false)),
    });
  });

  await page.goto("/app/?devTelegramId=900003#/media");
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "Повторить загрузку Медиа" }).click();
  await expect(page.getByRole("button", { name: "Присоединиться к медиаотделу" })).toBeVisible();
  expect(reads).toBe(2);
  expect(mediaWrites).toBe(0);
});

test("failed manager desk reads never expose stale tools; retry restores GET-only desk", async ({ page }) => {
  let deskReads = 0;
  let mediaWrites = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/media/") && request.method() !== "GET") mediaWrites += 1;
  });
  await page.route("**/api/v1/media/hub", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(mediaHub(true)),
  }));
  await page.route("**/api/v1/media/desk/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/content")) deskReads += 1;
    if (path.endsWith("/content") && deskReads === 1) {
      return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"temporary"}' });
    }
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify(path.endsWith("/channel-health") ? { ok: true, detail: "" } :
        path.endsWith("/today") || path.endsWith("/content") ? [] : {}),
    });
  });

  await page.goto("/app/?devTelegramId=900003#/media");
  await expect(page.getByRole("button", { name: "Повторить загрузку Медиа" })).toBeVisible();
  await expect(page.getByText("Управление медиа")).toHaveCount(0);
  await page.getByRole("button", { name: "Повторить загрузку Медиа" }).click();
  await expect(page.getByText("Управление медиа")).toBeVisible();
  expect(deskReads).toBe(2);
  expect(mediaWrites).toBe(0);
});
