import { expect, test } from "@playwright/test";

test("media knowledge prevents navigation to unsafe legacy external URLs", async ({ page }) => {
  let writes = 0;
  page.on("request", request => {
    if (request.url().includes("/api/v1/media/") && request.method() !== "GET") writes += 1;
  });
  const links = [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "https://user:password@t.me/era_leaders1/5",
    "https://t.me/era_leaders1/5",
  ];
  await page.route("**/api/v1/media/library**", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify(links.map((url, index) => ({
      id: 910000 + index, kind: "link", title: `Материал №${index}`,
      description: "Только браузерный mock", url,
      destination_type: "external_url", category: "guides",
      pinned: false, is_active: true, revision: 1,
    }))),
  }));
  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /База знаний.*Инструкции, шаблоны/ }).click();
  const safeLinks = page.getByRole("link", { name: "Открыть материал ↗" });
  await expect(safeLinks).toHaveCount(1);
  await expect(safeLinks.first()).toHaveAttribute("href", "https://t.me/era_leaders1/5");
  await expect(page.getByText("Ссылка материала имеет неподдерживаемый формат.")).toHaveCount(3);
  expect(writes).toBe(0);
});
