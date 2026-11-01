import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant can open professional portfolio and CV tools", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Моё портфолио/ }).click();

  await expect(page.getByRole("heading", { name: "Моё портфолио" })).toBeVisible();
  await expect(page.getByText("Всё, что ты сделал. Всё, что можешь показать.")).toBeVisible();
  await expect(page.getByRole("button", { name: "＋ Добавить результат" })).toBeVisible();
  await expect(page.getByText("Рекомендация ЭРА", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Отправить резюме в чат с ботом" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Скачать резюме PDF" })).toBeVisible();
  await expect(page.getByText(/Моего вектора/)).toBeVisible();
});


test("portfolio hides unsafe evidence links and wraps long mobile cards", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  const longTitle = "ОченьДлинноеНазваниеДостиженияБезПробеловДляПроверкиМобильнойКарточки";
  // Only the local E2E API response is modified; no participant or evidence
  // records are created or changed, and no external links are opened.
  await page.route("**/api/v1/career/dashboard", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const item = {
      item_type: "achievement", organization: "", description: "", issued_at: null,
      file_name: null, has_file: false, status: "self_reported",
      include_in_resume: false, admin_comment: null,
    };
    data.items = [
      { ...item, id: -901, title: longTitle, url: "javascript:alert(1)" },
      { ...item, id: -902, title: "Безопасное подтверждение", url: "https://example.org/era-evidence" },
      { ...item, id: -903, title: "Недопустимый формат", url: "data:text/html,unsafe" },
    ];
    await route.fulfill({ response, json: data });
  });

  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Моё портфолио/ }).click();
  await expect(page.getByText(longTitle)).toBeVisible();

  const links = page.getByRole("link", { name: "Открыть ссылку ↗" });
  await expect(links).toHaveCount(1);
  await expect(links).toHaveAttribute("href", "https://example.org/era-evidence");

  const card = page.getByText(longTitle).locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' era-card ')][1]");
  const fits = await card.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return rect.left >= 0 && rect.right <= window.innerWidth + 1
      && element.scrollWidth <= element.clientWidth + 1;
  });
  expect(fits).toBe(true);
});
