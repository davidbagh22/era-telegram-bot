import { expect, test } from "@playwright/test";

// Closes docs/FINAL_PRODUCTION_ACCEPTANCE.md item #269 ("Widths
// 320/360/390/430/768px checked") — every other spec runs at the single
// 390×844 viewport set in playwright.config.ts, which is the real device
// this app is built for, but never proves the layout survives the
// checklist's other five named widths. This spec is deliberately
// read-only (navigation + layout assertions only, no form submissions)
// so it can run against whatever state the other specs left the shared
// SQLite fixture DB in, without contending over it — see e2e/README.md's
// note on why workers is pinned to 1.
const WIDTHS = [320, 360, 390, 430, 768];
const PARTICIPANT_TELEGRAM_ID = 900001;

async function expectNoHorizontalOverflow(page: import("@playwright/test").Page, width: number) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  // +1px tolerance for sub-pixel rounding on some engines' scrollbar math.
  expect(scrollWidth, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(width + 1);
}

for (const width of WIDTHS) {
  test(`layout has no horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

    await expect(page.getByRole("heading", { name: "Привет, E2E Participant" })).toBeVisible();
    await expectNoHorizontalOverflow(page, width);

    // All five bottom-nav destinations, not just the landing screen — a
    // screen-specific layout bug (a wide table, an unwrapped label) is
    // exactly what a single-screen check would miss.
    for (const tabName of ["Активность", "Проекты", "Возможности", "Профиль", "Главная"]) {
      await page.getByRole("button", { name: tabName, exact: true }).click();
      await expectNoHorizontalOverflow(page, width);
    }
  });
}
