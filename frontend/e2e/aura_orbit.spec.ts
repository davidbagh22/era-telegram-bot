import { expect, test } from "@playwright/test";

test.use({ video: "on" });
test("invalid literature identifiers do not silently open the archive", async ({ page }) => {
  await page.goto("/app/?devTelegramId=900001#/literature/0");
  await expect(page.getByRole("heading", { name: "Этот объект больше недоступен" })).toBeVisible();
  await page.getByRole("button", { name: "На главную", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
});

test("orbit persists across sections; pause and reduced motion stop decorative work", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/app/?devTelegramId=900001");
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
  const ambient = await page.locator(".era-orbit-ambient").elementHandle();
  const nav = page.getByRole("navigation", { name: "Основная навигация" });
  await expect(nav.getByRole("button")).toHaveText(["Орбита", "Афиша", "Проекты", "Открытия", "Я"]);
  for (const label of ["Афиша", "Открытия", "Я", "Орбита"]) {
    await nav.getByRole("button", { name: label, exact: true }).click();
    await expect.poll(() => ambient!.evaluate(el => el.isConnected)).toBe(true);
  }
  await page.getByRole("button", { name: "Пауза живого фона" }).click();
  const blob = page.locator(".era-orbit-ambient__blob--a");
  await expect(blob).toHaveCSS("animation-play-state", "paused");
  const before = await blob.evaluate(el => el.getAnimations()[0]?.currentTime);
  await page.waitForTimeout(250);
  expect(await blob.evaluate(el => el.getAnimations()[0]?.currentTime)).toBe(before);
  await page.getByRole("button", { name: "Включить живой фон" }).click();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "true");
});

test("discover reaches the real reading archive and fits mobile widths", async ({ page }, info) => {
  await page.goto("/app/?devTelegramId=900001");
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
  await expect(page.locator(".era-skeleton")).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: info.outputPath("aura-orbit-home.png"), fullPage: true });
  const nav = page.getByRole("navigation", { name: "Основная навигация" });
  await nav.getByRole("button", { name: "Открытия" }).click();
  await expect(page.getByRole("heading", { name: "Открытия", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Досуг", exact: true }).click();
  await page.getByRole("button", { name: /Пять минут для себя/ }).click();
  await expect(page.getByRole("heading", { name: "Литература", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Последний доступный выпуск/ }).click();
  await expect(page.getByRole("article")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Другой взгляд", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("aura-reader.png"), fullPage: true });
  for (const width of [320, 390, 430]) {
    await page.setViewportSize({ width, height: 844 });
    for (const route of ["home", "events", "projects", "discover", "profile"]) {
      await page.goto("/app/?devTelegramId=900001#/" + route);
      await expect(nav).toBeVisible();
      await expect(page.locator(".era-page h1").first()).toBeVisible();
      await expect(page.locator(".era-skeleton")).toHaveCount(0);
      await page.evaluate(() => document.fonts.ready);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), route + " at " + width).toBe(false);
      if (width === 390) await page.screenshot({ path: info.outputPath("aura-" + route + ".png"), fullPage: true });
    }
  }
});
