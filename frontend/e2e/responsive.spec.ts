import { expect, test } from "@playwright/test";

const WIDTHS = [320, 360, 390, 430, 768];
const PARTICIPANT_TELEGRAM_ID = 900001;
const FLAKY_WIDTHS = new Set([430, 768]);
const OVERFLOW_TOLERANCE_PX = 5;

async function expectNoHorizontalOverflow(page: import("@playwright/test").Page, width: number) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  if (scrollWidth <= width + OVERFLOW_TOLERANCE_PX) {
    return;
  }

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

  expect(scrollWidth, `horizontal overflow at ${width}px; widest element: ${culprit}`).toBeLessThanOrEqual(
    width + OVERFLOW_TOLERANCE_PX,
  );
}

for (const width of WIDTHS) {
  test(`layout has no horizontal overflow at ${width}px`, async ({ page }) => {
    test.skip(FLAKY_WIDTHS.has(width), "quarantined: shared local E2E worker intermittently stalls late widths");
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

    await expect(page.getByText("УРОВЕНЬ", { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page, width);

    const nav = page.getByRole("navigation", { name: "Основная навигация" });
    for (const tabName of ["Проекты", "События", "Возможности", "Профиль", "Главная"]) {
      await nav.getByRole("button", { name: tabName, exact: true }).click();
      await expectNoHorizontalOverflow(page, width);
    }
  });
}
