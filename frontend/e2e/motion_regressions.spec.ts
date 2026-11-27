import { expect, test, type Page } from "@playwright/test";
import { installTelegramStub, setAppActive } from "./helpers_telegram";

const PARTICIPANT = 900001;

async function openHome(page: Page) {
  await installTelegramStub(page);
  await page.goto(`/app/?devTelegramId=${PARTICIPANT}#/home`);
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
  // Entrance animations are 260ms + up to 90ms stagger.
  await page.waitForTimeout(900);
}

const infiniteRunning = (page: Page) =>
  page.evaluate(() =>
    document.getAnimations().filter(
      (a) => a.playState === "running" && a.effect?.getComputedTiming?.().iterations === Infinity,
    ).length,
  );

test.describe("home orbit, screen transitions and panels", () => {
  test("after the entrance no screen root keeps a transform (fixed children stay viewport-anchored)", async ({ page }) => {
    await openHome(page);
    const leftovers = await page.evaluate(() => {
      const bad: string[] = [];
      for (const el of document.querySelectorAll<HTMLElement>(".era-page, .era-page > *")) {
        const cs = getComputedStyle(el);
        if (cs.transform !== "none") bad.push(`${el.tagName}.${el.className}: ${cs.transform}`);
        if (cs.willChange.includes("transform")) bad.push(`${el.tagName}: will-change ${cs.willChange}`);
      }
      return bad;
    });
    expect(leftovers).toEqual([]);
  });

  test("bottom sheet is pinned to the viewport even when the page is scrolled", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 600 });
    await installTelegramStub(page);
    await page.goto(`/app/?devTelegramId=${PARTICIPANT}#/profile`);
    const trigger = page.getByText("Запросить удаление аккаунта");
    await expect(trigger).toBeVisible();
    await page.waitForTimeout(700);
    await trigger.scrollIntoViewIfNeeded();
    await trigger.click();
    const sheet = page.locator(".era-bottom-sheet");
    await expect(sheet).toBeVisible();
    await page.waitForTimeout(400);
    const geometry = await page.evaluate(() => {
      const sheetBox = document.querySelector(".era-bottom-sheet")!.getBoundingClientRect();
      const backdrop = document.querySelector(".era-overlay-backdrop")!.getBoundingClientRect();
      return { sheetBottom: sheetBox.bottom, sheetTop: sheetBox.top, backdropTop: backdrop.top, backdropBottom: backdrop.bottom, vh: window.innerHeight };
    });
    expect(Math.round(geometry.sheetBottom)).toBe(geometry.vh);
    expect(geometry.sheetTop).toBeGreaterThanOrEqual(0);
    expect(Math.round(geometry.backdropTop)).toBe(0);
    expect(Math.round(geometry.backdropBottom)).toBe(geometry.vh);
  });

  test("first launch plays the orbit; re-opening from Telegram pauses then resumes the same animation", async ({ page }) => {
    await openHome(page);
    expect(await infiniteRunning(page)).toBeGreaterThan(0);
    await page.evaluate(() => {
      const w = window as unknown as Record<string, unknown>;
      w.__orbit = document.querySelector(".era-orbit-navigator");
      w.__ambient = document.querySelector(".era-orbit-ambient");
      w.__skeletonSeen = false;
      new MutationObserver(() => {
        if (document.querySelector('[aria-label="Загрузка орбиты"], [role="status"][aria-busy="true"]')) w.__skeletonSeen = true;
      }).observe(document.body, { childList: true, subtree: true });
    });
    const shellTime = () => page.evaluate(() => {
      const shell = document.querySelector(".era-orbit-node__shell")!;
      const anim = shell.getAnimations().find((a) => (a as CSSAnimation).animationName === "era-orbit-node-breathe")!;
      return { time: Number(anim.currentTime), state: anim.playState };
    });

    await page.waitForTimeout(400);
    const before = await shellTime();
    expect(before.state).toBe("running");

    await setAppActive(page, false);
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "true");
    await expect(page.locator(".era-orbit-node").first()).toHaveAttribute("data-paused", "true");
    const paused = await shellTime();
    expect(paused.state).toBe("paused");
    await page.waitForTimeout(300);
    expect((await shellTime()).time).toBe(paused.time);

    await setAppActive(page, true);
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "false");
    await page.waitForTimeout(300);
    const resumed = await shellTime();
    expect(resumed.state).toBe("running");
    // Resumed from where it stopped; a restart would drop the clock back to ~0.
    expect(resumed.time).toBeGreaterThanOrEqual(paused.time);

    const afterReopen = await page.evaluate(() => {
      const w = window as unknown as Record<string, unknown>;
      return {
        sameOrbit: document.querySelector(".era-orbit-navigator") === w.__orbit,
        sameAmbient: document.querySelector(".era-orbit-ambient") === w.__ambient,
        skeleton: w.__skeletonSeen,
        restartedEntrances: document.getAnimations().filter(
          (a) => (a as CSSAnimation).animationName === "era-card-in" && a.playState === "running",
        ).length,
      };
    });
    expect(afterReopen).toEqual({ sameOrbit: true, sameAmbient: true, skeleton: false, restartedEntrances: 0 });
  });

  test("prefers-reduced-motion removes ambient and orbit movement", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openHome(page);
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "true");
    expect(await infiniteRunning(page)).toBe(0);
    const names = await page.evaluate(() => ({
      shell: getComputedStyle(document.querySelector(".era-orbit-node__shell")!).animationName,
      blob: getComputedStyle(document.querySelector(".era-orbit-ambient__blob")!).animationName,
    }));
    expect(names).toEqual({ shell: "none", blob: "none" });
  });

  test("returning to Home paints cached content instead of replaying a skeleton", async ({ page }) => {
    await openHome(page);
    await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Афиша", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Афиша", exact: true })).toBeVisible();
    await page.evaluate(() => {
      const w = window as unknown as Record<string, unknown>;
      w.__skeletonOnReturn = false;
      new MutationObserver(() => {
        if (document.querySelector('[aria-label="Загрузка орбиты"]')) w.__skeletonOnReturn = true;
      }).observe(document.body, { childList: true, subtree: true });
    });
    await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Орбита", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
    await page.waitForTimeout(600);
    expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).__skeletonOnReturn)).toBe(false);
  });

  test("late-arriving cards do not re-trigger the entrance of cards already on screen", async ({ page }) => {
    await page.route(/\/api\/v1\/home\/daily-quote/, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1100));
      await route.continue();
    });
    await installTelegramStub(page);
    await page.goto(`/app/?devTelegramId=${PARTICIPANT}#/home`);
    await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
    await page.waitForTimeout(800);
    await page.evaluate(() => {
      (window as unknown as Record<string, unknown>).__restarts = 0;
      new MutationObserver(() => {
        const running = document.getAnimations().filter((a) => (a as CSSAnimation).animationName === "era-card-in" && a.playState === "running");
        (window as unknown as Record<string, number>).__restarts += running.length;
      }).observe(document.body, { childList: true, subtree: true, attributes: true });
    });
    await page.waitForTimeout(1800);
    expect(await page.evaluate(() => (window as unknown as Record<string, number>).__restarts)).toBe(0);
  });
});
