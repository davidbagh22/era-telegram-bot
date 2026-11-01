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
    if (request.method() !== "PATCH" || !/\\/api\\/v1\\/admin\\/events\\/\\d+\\/draft$/.test(request.url())) return false;
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
});
