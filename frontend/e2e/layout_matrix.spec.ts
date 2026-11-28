import { expect, test, type Page } from "@playwright/test";

/**
 * Mobile layout matrix: home, events (+detail), tasks, profile (+portfolio) and
 * admin at the four phone widths the Mini App targets, with long titles and
 * enlarged text. Real seeded backend; list responses are rewritten in the
 * browser only (no production data, no writes).
 */

const WIDTHS = [320, 360, 390, 430];
const FONT_SCALES = [1, 1.3, 1.5];
const PARTICIPANT = 900001;
const ADMIN = 900003;
const LONG_TITLE =
  "Сверхдлинное_название_межрегионального_форума_без_пробелов и ещё очень длинная фраза для проверки переноса строк";

async function expectNoHorizontalOverflow(page: Page, label: string) {
  const metrics = await page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement;
    return { scrollWidth: root.scrollWidth, innerWidth: window.innerWidth };
  });
  expect(metrics.scrollWidth, `${label}: horizontal overflow`).toBeLessThanOrEqual(metrics.innerWidth);
}

/** Interactive controls and headings must sit inside the viewport (catches content clipped by `overflow-x: clip`). */
async function expectControlsInsideViewport(page: Page, label: string) {
  const offenders = await page.evaluate(() => {
    const vw = window.innerWidth;
    const bad: string[] = [];
    const nodes = document.querySelectorAll<HTMLElement>(
      "button, a[href], input, select, textarea, [role=button], h1, h2, h3, label",
    );
    for (const el of nodes) {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      if (el.closest(".era-sr-only, .era-orbit-ambient, [aria-hidden='true'], [hidden]")) continue;
      let scroller: HTMLElement | null = el.parentElement;
      let inScroller = false;
      while (scroller) {
        const ox = getComputedStyle(scroller).overflowX;
        if (ox === "auto" || ox === "scroll") { inScroller = true; break; }
        scroller = scroller.parentElement;
      }
      if (inScroller) continue;
      if (rect.left < -1 || rect.right > vw + 1) {
        const text = (el.innerText || el.getAttribute("aria-label") || "").trim().slice(0, 40);
        bad.push(`${el.tagName.toLowerCase()}[${text}] ${Math.round(rect.left)}..${Math.round(rect.right)} of ${vw}`);
      }
    }
    return bad.slice(0, 6);
  });
  expect(offenders, `${label}: controls outside viewport`).toEqual([]);
}

async function expectNavClear(page: Page, label: string) {
  const viewport = page.viewportSize();
  if (!viewport) return;
  for (const name of ["Основная навигация", "Разделы управления ЭРА"]) {
    const nav = page.getByRole("navigation", { name });
    if ((await nav.count()) === 0) continue;
    const box = await nav.boundingBox();
    if (!box) continue;
    expect(box.x, `${label}: ${name} left`).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width, `${label}: ${name} right`).toBeLessThanOrEqual(viewport.width);
    // Pinned bars must be on screen without scrolling.
    expect(box.y + box.height, `${label}: ${name} bottom`).toBeLessThanOrEqual(viewport.height);
  }
}

async function check(page: Page, label: string) {
  await page.waitForTimeout(250);
  await expectNoHorizontalOverflow(page, label);
  await expectControlsInsideViewport(page, label);
  await expectNavClear(page, label);
}

function longTitles(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(longTitles);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, inner]) =>
        key === "title" && typeof inner === "string" && inner.length > 2 ? [key, LONG_TITLE] : [key, longTitles(inner)],
      ),
    );
  }
  return value;
}

async function installLongTitles(page: Page) {
  await page.route(/\/api\/v1\/(events|home|tasks|projects)(\/|\?|$)/, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    if (!response.ok()) return route.fulfill({ response });
    await route.fulfill({ response, json: longTitles(await response.json()) });
  });
}

async function setFontScale(page: Page, scale: number) {
  await page.addStyleTag({ content: `html { font-size: ${scale * 100}% !important; }` });
}

for (const width of WIDTHS) {
  for (const scale of FONT_SCALES) {
    test(`participant screens fit ${width}px at ${Math.round(scale * 100)}% text with long titles`, async ({ page }) => {
      await page.setViewportSize({ width, height: 780 });
      await installLongTitles(page);
      await page.goto(`/app/?devTelegramId=${PARTICIPANT}#/home`);
      await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
      if (scale !== 1) await setFontScale(page, scale);
      await check(page, `home ${width}/${scale}`);

      await page.evaluate(() => { window.location.hash = "#/events"; });
      await expect(page.getByRole("heading", { name: "Афиша", exact: true })).toBeVisible();
      await check(page, `events ${width}/${scale}`);

      await page.locator(".era-typography-feed-card").first().click();
      await expect(page.getByRole("button", { name: /Участвовать|Отказаться|Вы участвуете|очеред|Регистрация не нужна/i }).first()).toBeVisible();
      await check(page, `event detail ${width}/${scale}`);

      await page.evaluate(() => { window.location.hash = "#/tasks"; });
      await expect(page.getByRole("heading", { name: "Задания" })).toBeVisible();
      await check(page, `tasks ${width}/${scale}`);

      await page.evaluate(() => { window.location.hash = "#/projects"; });
      await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
      await check(page, `projects ${width}/${scale}`);

      await page.evaluate(() => { window.location.hash = "#/discover"; });
      await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
      await check(page, `discover ${width}/${scale}`);

      await page.evaluate(() => { window.location.hash = "#/opportunities"; });
      await expect(page.getByRole("heading", { name: "Возможности" })).toBeVisible();
      await check(page, `opportunities ${width}/${scale}`);

      await page.evaluate(() => { window.location.hash = "#/profile"; });
      await expect(page.getByRole("heading", { name: "Оформление" })).toBeVisible();
      await check(page, `profile ${width}/${scale}`);

      await page.getByRole("button", { name: "Изменить" }).click();
      await expect(page.getByLabel("Код цвета")).toBeVisible();
      await check(page, `profile appearance ${width}/${scale}`);

      await page.getByRole("button", { name: /Моё портфолио/ }).click();
      await expect(page.getByRole("button", { name: /Назад|←/ }).first()).toBeVisible();
      await check(page, `portfolio ${width}/${scale}`);
    });

    test(`admin workspace fits ${width}px at ${Math.round(scale * 100)}% text`, async ({ page }) => {
      await page.setViewportSize({ width, height: 780 });
      await page.goto(`/app/?devTelegramId=${ADMIN}#/admin`);
      await expect(page.getByRole("heading", { name: "Что происходит в ЭРА" })).toBeVisible();
      if (scale !== 1) await setFontScale(page, scale);
      await check(page, `admin overview ${width}/${scale}`);

      const sections = page.getByRole("navigation", { name: "Разделы управления ЭРА" }).getByRole("button");
      const count = await sections.count();
      for (let index = 0; index < count; index += 1) {
        const section = sections.nth(index);
        const name = ((await section.innerText()) || `section ${index}`).replace(/\s+/g, " ").trim();
        await section.click();
        await check(page, `admin ${name} ${width}/${scale}`);
      }
    });
  }
}
