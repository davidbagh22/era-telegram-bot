import { expect, test } from "@playwright/test";

test("calendar editor confirmation limits editing to one area and revocation closes an open form", async ({ page, browser, request }) => {
  const auth = async (id: number) => {
    const response = await request.post("/api/v1/miniapp/auth", { data: { initData: "", devTelegramId: id } });
    expect(response.ok()).toBeTruthy();
    return { Authorization: `Bearer ${(await response.json()).token}` };
  };
  const editorHeaders = await auth(900020);
  expect((await request.post("/api/v1/media/join", { headers: editorHeaders })).ok()).toBeTruthy();
  await page.goto("/app/?devTelegramId=900003#/media/era");
  await page.getByRole("button", { name: "Редакторы календаря", exact: true }).click();
  await page.getByLabel("Новый редактор", { exact: true }).selectOption({ label: "E2E Media Editor" });
  await page.getByRole("button", { name: "Назначить редактора", exact: true }).click();
  await expect(page.getByRole("group", { name: "Подтверждение полномочий" })).toContainText("Предоставить доступ к календарю ЭРА: E2E Media Editor?");
  const adminHeaders = await auth(900003);
  expect((await (await request.get("/api/v1/media/workspaces/era/editors", { headers: adminHeaders })).json()).editors).toEqual([]);
  await page.getByRole("button", { name: "Подтвердить полномочия", exact: true }).click();
  const revoke = page.getByRole("button", { name: "Снять доступ: E2E Media Editor", exact: true });
  await expect(revoke).toBeVisible();
  const context = await browser.newContext();
  try {
    const editor = await context.newPage();
    await editor.goto("/app/?devTelegramId=900020#/media/era");
    await expect(editor.getByRole("button", { name: "+ Добавить материал", exact: true })).toBeVisible();
    await expect(editor.getByRole("button", { name: "Редакторы календаря", exact: true })).toHaveCount(0);
    await editor.getByRole("button", { name: "+ Добавить материал", exact: true }).click();
    await editor.getByLabel("Название", { exact: true }).fill(`Материал редактора ${Date.now()}`);
    await editor.getByRole("button", { name: "Сохранить в календаре", exact: true }).click();
    await expect(editor.getByText(/Материал редактора \d+/)).toBeVisible();
    await editor.goto("/app/?devTelegramId=900020#/media/ksoors");
    await expect(editor.getByRole("heading", { name: "Контент-план", exact: true })).toBeVisible();
    await expect(editor.getByRole("button", { name: "+ Добавить материал", exact: true })).toHaveCount(0);
    await editor.goto("/app/?devTelegramId=900020#/media/era");
    await editor.getByRole("button", { name: "+ Добавить материал", exact: true }).click();
    await editor.getByLabel("Название", { exact: true }).fill("Старая форма после отзыва");
    await revoke.click();
    await page.getByRole("button", { name: "Подтвердить полномочия", exact: true }).click();
    await expect(revoke).toHaveCount(0);
    await editor.getByRole("button", { name: "Сохранить в календаре", exact: true }).click();
    await expect(editor.getByRole("alert")).toContainText("Доступ к календарю медиаотдела закрыт");
    await editor.reload();
    await expect(editor.getByRole("heading", { name: "Контент-план", exact: true })).toBeVisible();
    await expect(editor.getByRole("button", { name: "+ Добавить материал", exact: true })).toHaveCount(0);
    for (const width of [320, 430, 768]) {
      await page.setViewportSize({ width, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    }
  } finally { await context.close(); }
});
