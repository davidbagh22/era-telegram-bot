import { expect, test } from "@playwright/test";

test("media calendar never turns unsafe publication URLs into clickable links", async ({ page }) => {
  let writes = 0;
  page.on("request", request => {
    if (request.url().includes("/api/v1/media/workspaces/") && request.method() !== "GET") writes += 1;
  });
  await page.route("**/api/v1/media/workspaces", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: "era", title: "ЭРА", platforms: { telegram: "javascript:alert(1)", instagram: "https://instagram.com/era_leaders" },
      topic_url: "", can_manage: true, can_assign_editors: true }]),
  }));
  const source = [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "https://user:secret@t.me/era_leaders1/10",
    "https://t.me/era_leaders1/10",
  ];
  const entries = source.map((publication_url, index) => ({
    id: 900100 + index, area: "era", title: `Публикация №${index}`,
    body: "", platform: "telegram", status: "published", scheduled_at: null,
    responsible_id: null, materials: "", publication_url,
    publication_evidence: null, revision: 1,
  }));
  await page.route("**/api/v1/media/workspaces/era/calendar?**", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(entries),
  }));
  await page.route("**/api/v1/media/workspaces/era/team", route => route.fulfill({
    status: 200, contentType: "application/json", body: "[]",
  }));

  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /^ЭРА →/ }).click();
  const links = page.getByRole("link", { name: "Открыть публикацию ↗" });
  await expect(links).toHaveCount(1);
  await expect(links.first()).toHaveAttribute("href", "https://t.me/era_leaders1/10");
  await expect(page.getByText("Ссылка публикации имеет неподдерживаемый формат.")).toHaveCount(3);
  await expect(page.getByRole("link", { name: "Telegram ↗" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Instagram ↗" })).toHaveAttribute("href", "https://instagram.com/era_leaders");
  expect(writes).toBe(0);
});
