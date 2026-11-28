import { expect, test, type Page } from "@playwright/test";
import { installTelegramStub, setAppActive } from "./helpers_telegram";

const PARTICIPANT = 900001;

async function openHome(page: Page, opts: { initialActive?: boolean } = {}) {
  await installTelegramStub(page, opts);
  await page.goto(`/app/?devTelegramId=${PARTICIPANT}#/home`);
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
  await page.waitForTimeout(350);
}

async function sampleMotionTransforms(page: Page) {
  return page.evaluate(() => {
    const read = (selector: string) => {
      const el = document.querySelector<HTMLElement>(selector);
      if (!el) return null;
      const cs = getComputedStyle(el);
      return {
        transform: cs.transform,
        animationName: cs.animationName,
        playState: cs.animationPlayState,
      };
    };
    return {
      blobA: read(".era-orbit-ambient__blob--a"),
      arc: read(".era-orbit-ambient__arc"),
      ring: read(".era-orbit-navigator__ring"),
      shell: read(".era-orbit-node__shell"),
      content: read(".era-orbit-node__content"),
    };
  });
}

test.describe("iOS WebKit & Chromium home orbit motion", () => {
  test("live background visibly animates orbit and ambient elements with clear playing control", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await openHome(page);

    const toggle = page.locator("header button[data-motion-state]");
    await expect(toggle).toHaveAttribute("data-motion-state", "playing");
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    await expect(toggle).toContainText("Играет");
    await expect(page.getByTestId("reduced-motion-notice")).toHaveCount(0);

    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "false");
    await expect(page.locator(".era-orbit-navigator")).toHaveAttribute("data-paused", "false");

    const before = await sampleMotionTransforms(page);
    expect(before.blobA?.playState).toBe("running");
    expect(before.ring?.playState).toBe("running");
    expect(before.shell?.playState).toBe("running");
    expect(before.content?.playState).toBe("running");
    expect(before.shell?.animationName).toBe("era-orbit-node-breathe");
    expect(before.content?.animationName).toBe("era-orbit-node-float");

    await page.waitForTimeout(700);
    const after = await sampleMotionTransforms(page);

    expect(after.blobA?.transform).not.toBe(before.blobA?.transform);
    expect(after.arc?.transform).not.toBe(before.arc?.transform);
    expect(after.ring?.transform).not.toBe(before.ring?.transform);
    expect(after.shell?.transform).not.toBe(before.shell?.transform);
    expect(after.content?.transform).not.toBe(before.content?.transform);
  });

  test("pause/play button switches state, freezes motion, syncs with Profile and persists", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await openHome(page);

    const toggle = page.locator("header button[data-motion-state]");
    await expect(toggle).toHaveAttribute("data-motion-state", "playing");

    await toggle.click();
    await expect(toggle).toHaveAttribute("data-motion-state", "paused");
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(toggle).toContainText("Пауза");
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "true");
    await expect(page.locator(".era-orbit-navigator")).toHaveAttribute("data-paused", "true");

    const pausedSample = await sampleMotionTransforms(page);
    expect(pausedSample.blobA?.playState).toBe("paused");
    expect(pausedSample.ring?.playState).toBe("paused");
    expect(pausedSample.shell?.playState).toBe("paused");
    expect(pausedSample.content?.playState).toBe("paused");

    await page.waitForTimeout(450);
    const pausedLater = await sampleMotionTransforms(page);
    expect(pausedLater.shell?.transform).toBe(pausedSample.shell?.transform);
    expect(pausedLater.ring?.transform).toBe(pausedSample.ring?.transform);

    // Syncs with Profile -> Оформление.
    await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Я", exact: true }).click();
    const profileMotionBtn = page.locator("button[data-motion-state]");
    await expect(profileMotionBtn).toContainText("Живой фон · На паузе");
    await expect(profileMotionBtn).toHaveAttribute("data-motion-state", "paused");

    // Persists across reload.
    await page.reload();
    await expect(page.locator("button[data-motion-state]")).toContainText("Живой фон · На паузе");

    // Re-enabling from Profile resumes Home orbit.
    await page.locator("button[data-motion-state]").click();
    await expect(page.locator("button[data-motion-state]")).toContainText("Живой фон · Включён");
    await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Орбита", exact: true }).click();
    await expect(page.locator("header button[data-motion-state]")).toHaveAttribute("data-motion-state", "playing");
    await expect(page.locator("header button[data-motion-state]")).toContainText("Играет");
    await expect(page.locator(".era-orbit-navigator")).toHaveAttribute("data-paused", "false");
  });

  test("prefers-reduced-motion stops animations and explains why in Home and Profile", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openHome(page);

    const toggle = page.locator("header button[data-motion-state]");
    await expect(toggle).toHaveAttribute("data-motion-state", "reduced-motion");
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(toggle).toContainText("Статика");

    await expect(page.getByTestId("reduced-motion-notice")).toBeVisible();
    await expect(page.getByTestId("reduced-motion-notice")).toContainText("Уменьшение движения");

    const sample = await sampleMotionTransforms(page);
    expect(sample.blobA?.animationName).toBe("none");
    expect(sample.ring?.animationName).toBe("none");
    expect(sample.shell?.animationName).toBe("none");
    expect(sample.content?.animationName).toBe("none");

    // Orbit ring stays centered around "ЭРА" even with animations disabled.
    const ringGeometry = await page.evaluate(() => {
      const ring = document.querySelector(".era-orbit-navigator__ring")!.getBoundingClientRect();
      const center = document.querySelector(".era-orbit-navigator__center")!.getBoundingClientRect();
      return {
        dx: Math.abs((ring.left + ring.width / 2) - (center.left + center.width / 2)),
        dy: Math.abs((ring.top + ring.height / 2) - (center.top + center.height / 2)),
        overflowX: document.documentElement.scrollWidth > window.innerWidth,
      };
    });
    expect(ringGeometry.dx).toBeLessThanOrEqual(2);
    expect(ringGeometry.dy).toBeLessThanOrEqual(2);
    expect(ringGeometry.overflowX).toBe(false);

    // Tapping the button explains the OS setting via toast instead of pretending to toggle.
    await toggle.click();
    await expect(page.locator(".era-toast")).toContainText("Уменьшение движения");

    // Profile also reflects system override instead of showing "Включён".
    await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Я", exact: true }).click();
    const profileMotionBtn = page.locator("button[data-motion-state]");
    await expect(profileMotionBtn).toHaveAttribute("data-motion-state", "reduced-motion");
    await expect(profileMotionBtn).toContainText("Живой фон · Остановлен системой");
    await expect(profileMotionBtn).toBeDisabled();
    await expect(page.getByTestId("appearance-reduced-motion-note")).toContainText("Уменьшение движения");
  });

  test("iOS Telegram WebView recovers when isActive starts false or deactivated fires without activated", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    // Simulate iOS Telegram Mini App launching with isActive === false while page is visible.
    await openHome(page, { initialActive: false });

    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "false");
    await expect(page.locator(".era-orbit-navigator")).toHaveAttribute("data-paused", "false");
    await expect(page.locator("header button[data-motion-state]")).toHaveAttribute("data-motion-state", "playing");

    // Simulate iOS transient deactivated event (e.g., notification banner) with no matching activated event.
    const toggle = page.locator("header button[data-motion-state]");
    await page.evaluate(() => {
      const emit = (window as unknown as { __tgEmit: (name: string, patch?: Record<string, unknown>) => void }).__tgEmit;
      emit("deactivated", { isActive: false });
    });
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "true");
    await expect(toggle).toHaveAttribute("data-motion-state", "paused");
    await expect(toggle).toContainText("Пауза");

    // Direct tap on the paused Home button must resume motion rather than persisting paused=false.
    await toggle.click();
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "false");
    await expect(toggle).toHaveAttribute("data-motion-state", "playing");
    await expect(toggle).toContainText("Играет");
    expect(await page.evaluate(() => localStorage.getItem("era.orbit.liveBackground"))).toBe("1");

    // Keyboard activation (Enter) on the paused button after another deactivated event must also resume.
    await toggle.focus();
    await page.evaluate(() => {
      const emit = (window as unknown as { __tgEmit: (name: string, patch?: Record<string, unknown>) => void }).__tgEmit;
      emit("deactivated", { isActive: false });
    });
    await expect(toggle).toHaveAttribute("data-motion-state", "paused");
    await page.keyboard.press("Enter");
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "false");
    await expect(toggle).toHaveAttribute("data-motion-state", "playing");
    expect(await page.evaluate(() => localStorage.getItem("era.orbit.liveBackground"))).toBe("1");

    // Interacting anywhere else on the visible screen (pointerdown) also recovers automatically.
    await page.evaluate(() => {
      const emit = (window as unknown as { __tgEmit: (name: string, patch?: Record<string, unknown>) => void }).__tgEmit;
      emit("deactivated", { isActive: false });
    });
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "true");
    await page.locator("h2", { hasText: "Твоя орбита" }).dispatchEvent("pointerdown");
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "false");
    await expect(toggle).toHaveAttribute("data-motion-state", "playing");

    // True backgrounding (hidden + deactivated) still pauses cleanly and resumes on re-activation.
    await setAppActive(page, false);
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "true");
    await setAppActive(page, true);
    await expect(page.locator(".era-orbit-ambient")).toHaveAttribute("data-paused", "false");
  });
});
