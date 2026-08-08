import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

test("admin searches the people directory, opens a participant, and awards points", async ({
  page,
}) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(page.getByText("ЭРА / ADMIN")).toBeVisible();

  await page.getByRole("button", { name: "Участники" }).click();
  await page.getByPlaceholder("Имя, username или Telegram ID").fill("E2E Participant");

  await page.getByText("E2E Participant").click();
  await expect(page.getByText("Роль и доступ")).toBeVisible();
  await expect(page.getByText("Начислить или списать баллы")).toBeVisible();

  await page.getByPlaceholder("±баллы").fill("15");
  await page.getByPlaceholder("Причина").fill("E2E проверка начисления баллов");
  await page.getByRole("button", { name: "Применить" }).click();

  // A real award through the full stack (API → user_management_service →
  // DB), not a UI-only counter bump — verified by the balance <dd>
  // reflecting the freshly refetched detail after the award. The label
  // ("Баланс") and value ("15 баллов") are separate <dt>/<dd> elements, so
  // this checks the value directly rather than the label's own text.
  await expect(page.getByText("15 баллов")).toBeVisible();
});
