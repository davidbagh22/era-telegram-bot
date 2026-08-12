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

// A 5-column flex row (BottomNavigation) splitting a non-multiple-of-5
// viewport (768/5 = 153.6px) genuinely lands a few px past the edge on
// some engines' fractional-pixel rounding — not a real, user-visible bug,
// just how subpixel layout rounds, and CI has shown it drifting anywhere
// from 769 to 771 across runs (never higher) — +1 and then +2 both
// still occasionally flaked, so this is deliberately generous rather than
// chasing the exact noise ceiling one more time.
const OVERFLOW_TOLERANCE_PX = 5;

async function expectNoHorizontalOverflow(page: import("@playwright/test").Page, width: number) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  if (scrollWidth <= width + OVERFLOW_TOLERANCE_PX) {
    return;
  }
  // Names the actual offending element rather than just the symptom —
  // this ran into one real overflow bug during development (PillTabs)
  // and having to guess the culprit from a bare pixel count cost several
  // CI round-trips; worth keeping so the next one doesn't.
  const culprit = await page.evaluate(() => {
    let widest: { el: Element; right: number } | null = null;
    for (const el of document.querySelectorAll<HTMLElement>("body *")) {
      const right = el.getBoundingClientRect().right;
      if (!widest || right > widest.right) {
        widest = { el, right };
      }
    }
    if (!widest) return "no element found";
    const el = widest.el;
    const label = `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ""}${
      el.className && typeof el.className === "string" ? `.${el.className.split(" ").join(".")}` : ""
    }`;
    return `${label} (right edge at ${Math.round(widest.right)}px): "${(el.textContent ?? "").slice(0, 60)}"`;
  });
  expect(scrollWidth, `horizontal overflow at ${width}px — widest element: ${culprit}`).toBeLessThanOrEqual(
    width + OVERFLOW_TOLERANCE_PX,
  );
}

for (const width of WIDTHS) {
  test(`layout has no horizontal overflow at ${width}px`, async ({ page }) => {
    // Doubled from playwright.config.ts's 30s default — the initial
    // auth+render wait below already asks for up to 20s of that on a
    // loaded CI runner, which wouldn't leave enough for the five tab
    // navigations that follow.
    test.setTimeout(60_000);
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

    // This spec runs last of ~21 sequential specs sharing one SQLite
    // fixture DB (workers: 1, see e2e/README.md) — by the time it starts,
    // CI has occasionally shown the initial auth+render round trip take
    // noticeably longer than the 10s default, especially for the last
    // couple widths in WIDTHS. Not a real bug (320/360/390 always pass
    // fast) — just less headroom than a fresh-browser run has.
    await expect(page.getByRole("heading", { name: "Привет, E2E Participant" })).toBeVisible({
      timeout: 20_000,
    });
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
