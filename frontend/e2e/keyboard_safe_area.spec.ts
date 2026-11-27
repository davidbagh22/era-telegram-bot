import { expect, test } from "@playwright/test";
import { installTelegramStub } from "./helpers_telegram";

const PARTICIPANT = 900001;
const ADMIN = 900003;

test("fixed bottom bars respect Telegram safe-area insets (notch and home indicator)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 780 });
  await installTelegramStub(page, { safeArea: { top: 47, bottom: 34 } });
  await page.goto(`/app/?devTelegramId=${PARTICIPANT}#/home`);
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();

  const geometry = await page.evaluate(() => {
    const nav = document.querySelector(".era-bottom-nav")!.getBoundingClientRect();
    const layout = document.querySelector(".era-user-layout") as HTMLElement;
    return {
      navBottomGap: window.innerHeight - nav.bottom,
      layoutPaddingTop: parseFloat(getComputedStyle(layout).paddingTop),
      safeTop: getComputedStyle(document.documentElement).getPropertyValue("--era-tg-top").trim(),
    };
  });
  expect(geometry.safeTop).toBe("47px");
  expect(geometry.layoutPaddingTop).toBeGreaterThanOrEqual(47);
  expect(geometry.navBottomGap).toBeGreaterThanOrEqual(34);
});

test("admin workspace header and section bar respect safe-area insets", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 780 });
  await installTelegramStub(page, { safeArea: { top: 47, bottom: 34 } });
  await page.goto(`/app/?devTelegramId=${ADMIN}#/admin`);
  const sections = page.getByRole("navigation", { name: "Разделы управления ЭРА" });
  await expect(sections).toBeVisible();
  const geometry = await page.evaluate(() => {
    const bar = document.querySelector('nav[aria-label="Разделы управления ЭРА"]')!.getBoundingClientRect();
    const header = document.querySelector("strong")!.getBoundingClientRect();
    return { barBottomGap: window.innerHeight - bar.bottom, headerTop: header.top };
  });
  expect(geometry.barBottomGap).toBeGreaterThanOrEqual(34);
  expect(geometry.headerTop).toBeGreaterThanOrEqual(47);
});

test("on-screen keyboard: bottom bars step aside and the focused field stays visible", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegramStub(page);
  await page.goto(`/app/?devTelegramId=${PARTICIPANT}#/profile`);
  await expect(page.getByRole("heading", { name: "Оформление" })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Основная навигация" });
  await expect(nav).toBeVisible();

  const hex = page.getByLabel("Код цвета");
  await hex.scrollIntoViewIfNeeded();
  await hex.focus();
  // Telegram Android shrinks the WebView; emulate the keyboard taking ~45% of the screen.
  await page.setViewportSize({ width: 390, height: 460 });
  await expect(page.locator("html")).toHaveAttribute("data-keyboard", "open");
  await expect(nav).toBeHidden();

  await expect.poll(async () => {
    const box = await hex.boundingBox();
    return box ? box.y >= 0 && box.y + box.height <= 460 : false;
  }).toBe(true);

  await hex.blur();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("html")).not.toHaveAttribute("data-keyboard", "open");
  await expect(nav).toBeVisible();
});

test("keyboard mode is not triggered by a short window without a focused field", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegramStub(page);
  await page.goto(`/app/?devTelegramId=${PARTICIPANT}#/home`);
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 460 });
  await page.waitForTimeout(300);
  await expect(page.locator("html")).not.toHaveAttribute("data-keyboard", "open");
  await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
});
