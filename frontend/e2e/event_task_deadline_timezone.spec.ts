import { expect, test } from "@playwright/test";

// Browser-only isolated CI fixture: never publishes an event or sends Telegram messages.
test.use({ timezoneId: "Asia/Yerevan" });

test("wizard task deadline persists an absolute instant and reopens in editor local time", async ({ page }) => {
  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Создать мероприятие.*Черновик/ }).click();
  await page.getByRole("button", { name: "＋ Создать мероприятие" }).click();
  await page.getByLabel("Название", { exact: true }).fill("E2E срок задания, только черновик");
  for (let step = 1; step < 7; step += 1) {
    await page.getByRole("button", { name: "Продолжить" }).click();
  }
  await expect(page.getByText("ШАГ 7 ИЗ 10")).toBeVisible();
  await page.getByRole("button", { name: "＋ Добавить задание" }).click();
  await page.getByLabel("Название", { exact: true }).fill("E2E проверка часового пояса");

  const savedRequest = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !new URL(request.url()).pathname.match(/^\/api\/v1\/admin\/events\/[0-9]+\/draft$/)) return false;
    const payload = request.postDataJSON();
    return payload.participant_tasks?.[0]?.deadline === "2026-11-07T14:00:00.000Z";
  });
  await page.getByLabel("Срок").fill("2026-11-07T18:00");
  await savedRequest;
  await expect(page.getByLabel("Срок")).toHaveValue("2026-11-07T18:00");
  await expect(page.getByText("Сохранено ✓", { exact: true })).toBeVisible();
  // A persisted UTC timestamp must round-trip to the same local wall-clock time.
  await page.getByRole("button", { name: "Сохранить черновик и выйти" }).click();
  await page.getByRole("button", { name: /E2E срок задания, только черновик.*Шаг 7/ }).click();
  await expect(page.getByLabel("Срок")).toHaveValue("2026-11-07T18:00");

  // A narrow Telegram viewport must not clip the date picker or points field.
  await page.setViewportSize({ width: 320, height: 720 });
  const deadline = await page.getByLabel("Срок").boundingBox();
  const points = await page.getByLabel("Баллы", { exact: true }).boundingBox();
  expect(deadline).not.toBeNull();
  expect(points).not.toBeNull();
  expect(deadline!.width).toBeGreaterThan(175);
  expect(deadline!.x).toBeGreaterThanOrEqual(0);
  expect(deadline!.x + deadline!.width).toBeLessThanOrEqual(321);
  expect(points!.x + points!.width).toBeLessThanOrEqual(321);
  expect(points!.y).toBeGreaterThan(deadline!.y);
});


test("wizard program time and presenter remain usable at 320px", async ({ page }) => {
  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Создать мероприятие.*Черновик/ }).click();
  await page.getByRole("button", { name: "＋ Создать мероприятие" }).click();
  await page.getByLabel("Название", { exact: true }).fill("E2E мобильная программа, только черновик");
  for (let step = 1; step < 6; step += 1) {
    await page.getByRole("button", { name: "Продолжить" }).click();
  }
  await expect(page.getByText("ШАГ 6 ИЗ 10")).toBeVisible();
  await page.getByRole("button", { name: "＋ Добавить активность" }).click();
  await page.setViewportSize({ width: 320, height: 720 });
  await page.getByLabel("Время").fill("14:30");
  await page.getByLabel("Ведущий").fill("E2E ведущий");
  const time = await page.getByLabel("Время").boundingBox();
  const presenter = await page.getByLabel("Ведущий").boundingBox();
  expect(time).not.toBeNull();
  expect(presenter).not.toBeNull();
  expect(time!.width).toBeGreaterThan(175);
  expect(time!.x).toBeGreaterThanOrEqual(0);
  expect(time!.x + time!.width).toBeLessThanOrEqual(321);
  expect(presenter!.x + presenter!.width).toBeLessThanOrEqual(321);
  expect(presenter!.y).toBeGreaterThan(time!.y);
  await expect(page.getByLabel("Время")).toHaveValue("14:30");
  await expect(page.getByLabel("Ведущий")).toHaveValue("E2E ведущий");
});
