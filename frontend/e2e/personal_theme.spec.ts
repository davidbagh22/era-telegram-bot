import { expect, test, type Page } from "@playwright/test";
import { DEFAULT_ACCENT, TEXT_CONTRAST, contrastRatio, deriveAccent } from "../src/theme/accent";
import { installTelegramStub } from "./helpers_telegram";

const USER_A = 900001;
const USER_B = 900002;
const BLUE = "#2f7cf6";
const SURFACE = "#321731";

async function tokenFor(page: Page, telegramId: number): Promise<string> {
  const response = await page.request.post("/api/v1/miniapp/auth", { data: { devTelegramId: telegramId } });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).token as string;
}

async function putAccent(page: Page, telegramId: number, accent: string | null) {
  const token = await tokenFor(page, telegramId);
  const response = await page.request.put("/api/v1/me/preferences", {
    headers: { Authorization: `Bearer ${token}` },
    data: { accent_color: accent },
  });
  expect(response.ok()).toBeTruthy();
}

async function getAccent(page: Page, telegramId: number): Promise<string | null> {
  const token = await tokenFor(page, telegramId);
  const response = await page.request.get("/api/v1/me/preferences", { headers: { Authorization: `Bearer ${token}` } });
  return (await response.json()).accent_color as string | null;
}

const rootVar = (page: Page, name: string) =>
  page.evaluate((n) => document.documentElement.style.getPropertyValue(n).trim(), name);

async function openAppearance(page: Page, telegramId: number) {
  await installTelegramStub(page);
  await page.goto(`/app/?devTelegramId=${telegramId}#/profile`);
  await expect(page.getByRole("heading", { name: "Оформление" })).toBeVisible();
}

test.describe("personal colour", () => {
  test.beforeEach(async ({ page }) => {
    await putAccent(page, USER_A, null);
    await putAccent(page, USER_B, null);
  });
  test.afterEach(async ({ page }) => {
    await putAccent(page, USER_A, null);
    await putAccent(page, USER_B, null);
  });

  test("preset applies instantly, previews live, persists to the server and survives reload", async ({ page }) => {
    await openAppearance(page, USER_A);
    expect(await rootVar(page, "--era-primary")).toBe("");

    await page.getByRole("button", { name: "Синий", exact: true }).click();
    const expected = deriveAccent(BLUE, "dark");
    await expect.poll(() => rootVar(page, "--era-primary")).toBe(expected.fill);
    expect(await rootVar(page, "--era-on-primary")).toBe(expected.onFill);
    await expect(page.getByRole("button", { name: "Синий", exact: true })).toHaveAttribute("aria-pressed", "true");

    const previewColor = await page.getByTestId("appearance-preview").evaluate((el) => (el as HTMLElement).style.getPropertyValue("--era-primary"));
    expect(previewColor).toBe(expected.fill);

    await expect(page.getByTestId("appearance-save-status")).toContainText("сохранён");
    expect(await getAccent(page, USER_A)).toBe(BLUE);
    expect(await page.evaluate(() => localStorage.getItem("era.accent.v1"))).toBe(BLUE);

    await page.reload();
    await expect(page.getByRole("heading", { name: "Оформление" })).toBeVisible();
    expect(await rootVar(page, "--era-primary")).toBe(expected.fill);
  });

  test("cached colour is applied before the app has authenticated (no flash of the default)", async ({ page }) => {
    await installTelegramStub(page);
    await page.addInitScript((hex) => localStorage.setItem("era.accent.v1", hex), BLUE);
    await page.route("**/api/v1/miniapp/auth", (route) => new Promise((resolve) => setTimeout(() => resolve(route.continue()), 1500)));
    await page.goto(`/app/?devTelegramId=${USER_A}#/home`);
    await expect(page.getByRole("status").filter({ hasText: "Загрузка ЭРА" })).toBeVisible();
    expect(await rootVar(page, "--era-primary")).toBe(deriveAccent(BLUE, "dark").fill);
  });

  test("colour follows the user to another device and stays isolated from other users", async ({ page, browser }) => {
    await putAccent(page, USER_A, "#2fa866");
    const otherDevice = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const deviceTwo = await otherDevice.newPage();
    await installTelegramStub(deviceTwo);
    await deviceTwo.goto(`/app/?devTelegramId=${USER_A}#/home`);
    await expect(deviceTwo.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
    await expect.poll(() => rootVar(deviceTwo, "--era-primary")).toBe(deriveAccent("#2fa866", "dark").fill);
    await otherDevice.close();

    const stranger = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const userB = await stranger.newPage();
    await installTelegramStub(userB);
    await userB.goto(`/app/?devTelegramId=${USER_B}#/home`);
    await expect(userB.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
    await userB.waitForTimeout(800);
    expect(await rootVar(userB, "--era-primary")).toBe("");
    await stranger.close();
  });

  test("custom hex is validated, applied, and «Вернуть цвет ЭРА» restores the brand colour everywhere", async ({ page }) => {
    await openAppearance(page, USER_A);
    const hex = page.getByLabel("Код цвета");

    await hex.fill("#12");
    await hex.fill("#zzzzzz");
    await expect(page.getByRole("alert")).toContainText("#RRGGBB");
    expect(await rootVar(page, "--era-primary")).toBe("");

    await hex.fill("#E53935");
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect.poll(() => rootVar(page, "--era-primary")).toBe(deriveAccent("#e53935", "dark").fill);
    await expect(page.getByTestId("appearance-save-status")).toContainText("сохранён");
    expect(await getAccent(page, USER_A)).toBe("#e53935");

    await page.getByRole("button", { name: "Вернуть цвет ЭРА" }).click();
    await expect.poll(() => rootVar(page, "--era-primary")).toBe("");
    expect(await rootVar(page, "--era-cyan")).toBe("");
    await expect(page.getByRole("button", { name: "Вернуть цвет ЭРА" })).toBeDisabled();
    await expect.poll(() => getAccent(page, USER_A)).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem("era.accent.v1"))).toBeNull();
    expect(DEFAULT_ACCENT).toBe("#bc2184");
  });

  test("typing a hex code character by character keeps the full value and saves only what was typed", async ({ page }) => {
    await openAppearance(page, USER_A);
    const hex = page.getByLabel("Код цвета");

    await hex.fill("");
    await hex.pressSequentially("#123456");
    await expect(hex).toHaveValue("#123456");
    await expect.poll(() => rootVar(page, "--era-primary")).toBe(deriveAccent("#123456", "dark").fill);
    await expect.poll(() => getAccent(page, USER_A)).toBe("#123456");

    await hex.fill("");
    await hex.pressSequentially("#abc");
    await expect(hex).toHaveValue("#abc");
    await expect(page.getByRole("alert")).toHaveCount(0);
    await hex.blur();
    await expect(hex).toHaveValue("#AABBCC");
    await expect.poll(() => rootVar(page, "--era-primary")).toBe(deriveAccent("#aabbcc", "dark").fill);
    await expect.poll(() => getAccent(page, USER_A)).toBe("#aabbcc");
  });

  test("hard colours stay readable on real controls: tabs, primary button, status chips", async ({ page }) => {
    await openAppearance(page, USER_A);
    const hex = page.getByLabel("Код цвета");
    for (const colour of ["#000000", "#ffffff", "#ffff00", "#0000ff", "#7f7f7f", "#b0722a"]) {
      await hex.fill(colour);
      await expect.poll(() => rootVar(page, "--era-primary")).toBe(deriveAccent(colour, "dark").fill);
      const measure = () => page.evaluate(() => {
        const preview = document.querySelector<HTMLElement>('[data-testid="appearance-preview"]')!;
        const button = preview.querySelector<HTMLElement>(".era-btn-primary")!;
        const selected = [...preview.querySelectorAll<HTMLElement>("span")].find((el) => el.textContent === "Выбрано")!;
        const rgb = (value: string) => value.match(/\d+(\.\d+)?/g)!.slice(0, 3).map(Number);
        const hexOf = (value: string) => `#${rgb(value).map((n) => Math.round(n).toString(16).padStart(2, "0")).join("")}`;
        return {
          buttonText: hexOf(getComputedStyle(button).color),
          fill: getComputedStyle(preview).getPropertyValue("--era-primary").trim(),
          chipText: hexOf(getComputedStyle(selected).color),
        };
      });
      // Colour transitions (200ms) must finish before measuring computed colours.
      await expect.poll(async () => {
        const m = await measure();
        return contrastRatio(m.buttonText, m.fill) >= TEXT_CONTRAST && contrastRatio(m.chipText, SURFACE) >= TEXT_CONTRAST;
      }, { message: `readable controls for ${colour}`, timeout: 3000 }).toBe(true);
    }
  });

  test("a failed save keeps the colour locally and retries on the next launch", async ({ page }) => {
    await openAppearance(page, USER_A);
    await page.route("**/api/v1/me/preferences", (route) =>
      route.request().method() === "PUT" ? route.abort("connectionfailed") : route.continue(),
    );
    await page.getByRole("button", { name: "Оранжевый", exact: true }).click();
    await expect(page.getByTestId("appearance-save-status")).toContainText("на других устройствах появится");
    expect(await getAccent(page, USER_A)).toBeNull();
    await page.unroute("**/api/v1/me/preferences");

    await page.reload();
    await expect(page.getByRole("heading", { name: "Оформление" })).toBeVisible();
    await expect.poll(() => getAccent(page, USER_A)).toBe("#f2711c");
  });
});
