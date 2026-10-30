import { expect, test } from "@playwright/test";

test("manager hides and restores an event without deleting registrations or republishing", async ({ page }) => {
  let listingVisible = true;
  const writes: Array<{ visible: boolean }> = [];
  let republished = 0;
  await page.route("**/api/v1/admin/events/operational", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{
      id: 4242, title: "E2E мероприятие", status: "published",
      event_date: "2026-11-07", event_time: "18:00", location: "Дом Москвы",
      registered: 3, free: 12, points_for_visit: 150,
      show_in_public_listing: true,
    }]),
  }));
  await page.route("**/api/v1/admin/events/4242/listing", async (route) => {
    const body = route.request().postDataJSON() as { visible: boolean };
    writes.push(body);
    listingVisible = body.visible;
    return route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ id: 4242, show_in_public_listing: listingVisible }) });
  });
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/publish")) republished += 1;
  });

  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();
  await expect(page.getByText(/Записано: 3/)).toBeVisible();

  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Скрыть из общей афиши" }).click();
  expect(writes).toHaveLength(0);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Скрыть из общей афиши" }).click();
  await expect(page.getByRole("button", { name: "Вернуть в общую афишу" })).toBeVisible();
  expect(writes).toEqual([{ visible: false }]);
  await expect(page.getByText(/Записано: 3/)).toBeVisible();

  await page.getByRole("button", { name: "Вернуть в общую афишу" }).click();
  await expect(page.getByRole("button", { name: "Скрыть из общей афиши" })).toBeVisible();
  expect(writes).toEqual([{ visible: false }, { visible: true }]);
  expect(republished).toBe(0);
});
