import { expect, test } from "@playwright/test";

// CI-only admin fixture: creates a disposable draft and never publishes it.
test("wizard date and start time fit a 320px Telegram viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Создать мероприятие.*Черновик/ }).click();
  await page.getByRole("button", { name: "＋ Создать мероприятие" }).click();
  await page.getByRole("button", { name: "Продолжить" }).click();
  await expect(page.getByText("ШАГ 2 ИЗ 10")).toBeVisible();

  const date = page.getByLabel("Дата", { exact: true });
  const start = page.getByLabel("Начало", { exact: true });
  await date.fill("2026-11-20");
  await start.fill("18:30");
  const end = page.getByLabel("Окончание", { exact: true });
  await end.fill("20:00");
  await expect(date).toHaveValue("2026-11-20");
  await expect(start).toHaveValue("18:30");
  await expect(end).toHaveValue("20:00");

  const [dateBox, startBox, endBox] = await Promise.all([date.boundingBox(), start.boundingBox(), end.boundingBox()]);
  expect(dateBox).not.toBeNull();
  expect(startBox).not.toBeNull();
  expect(endBox).not.toBeNull();
  if (!dateBox || !startBox || !endBox) return;
  for (const box of [dateBox, startBox, endBox]) {
    expect(box.width).toBeGreaterThan(160);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(321);
  }
  expect(dateBox.y + dateBox.height).toBeLessThanOrEqual(startBox.y + 1);
  expect(startBox.y + startBox.height).toBeLessThanOrEqual(endBox.y + 1);
});
