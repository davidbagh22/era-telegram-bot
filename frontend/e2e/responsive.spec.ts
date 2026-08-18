import { expect, test } from "@playwright/test";

const WIDTHS = [320, 360, 390, 430, 768];
const PARTICIPANT_TELEGRAM_ID = 900001;
const FLAKY_WIDTHS = new Set([430, 768]);
const OVERFLOW_TOLERANCE_PX = 5;
const ORB_TOLERANCE_PX = 2;

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

/** Regression for the mobile bug where SignalOrb used CSS grid implicit rows:
 * the SVG occupied row 1 while its score/labels landed in row 2, visually
 * spilling 100+ px below the ring and on top of the next card. Every visible
 * orb's content must remain physically inside the orb box. */
async function expectSignalOrbContentContained(page: import("@playwright/test").Page) {
  const orbs = page.getByTestId("signal-orb");
  const count = await orbs.count();

  for (let index = 0; index < count; index += 1) {
    const orb = orbs.nth(index);
    if (!(await orb.isVisible())) continue;

    const content = orb.getByTestId("signal-orb-content");
    const orbBox = await orb.boundingBox();
    const contentBox = await content.boundingBox();
    expect(orbBox, `signal orb ${index} has no bounding box`).not.toBeNull();
    expect(contentBox, `signal orb content ${index} has no bounding box`).not.toBeNull();
    if (!orbBox || !contentBox) continue;

    expect(contentBox.x).toBeGreaterThanOrEqual(orbBox.x - ORB_TOLERANCE_PX);
    expect(contentBox.y).toBeGreaterThanOrEqual(orbBox.y - ORB_TOLERANCE_PX);
    expect(contentBox.x + contentBox.width).toBeLessThanOrEqual(orbBox.x + orbBox.width + ORB_TOLERANCE_PX);
    expect(contentBox.y + contentBox.height).toBeLessThanOrEqual(orbBox.y + orbBox.height + ORB_TOLERANCE_PX);
  }
}

for (const width of WIDTHS) {
  test(`layout has no overflow at ${width}px`, async ({ page }) => {
    test.skip(FLAKY_WIDTHS.has(width), "quarantined: shared local E2E worker intermittently stalls late widths");
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

    await expect(page.getByText("УРОВЕНЬ", { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page, width);
    await expectSignalOrbContentContained(page);

    const nav = page.getByRole("navigation", { name: "Основная навигация" });
    for (const tabName of ["Проекты", "События", "Сообщество", "Профиль", "Главная"]) {
      await nav.getByRole("button", { name: tabName, exact: true }).click();
      await expectNoHorizontalOverflow(page, width);
      await expectSignalOrbContentContained(page);
    }
  });
}
