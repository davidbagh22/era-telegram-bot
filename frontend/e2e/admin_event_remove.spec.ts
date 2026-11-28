import { expect, test } from "@playwright/test";

const VIEWPORTS = [320, 390, 430] as const;

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-28T08:00:00Z"));
});

async function enterAdminEventsOperations(page: import("@playwright/test").Page) {
  await page.goto("/app/?devTelegramId=900003");
  await page
    .getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Я", exact: true })
    .click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Пульт руководителя", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Работа", exact: true }).click();
  await page.getByRole("button", { name: /^Мероприятия.*Создание/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();
}

test("admin can remove an event with registration-count confirmation and restore via undo (even when list empties)", async ({ page }) => {
  let removed = false;
  let cancelCalls = 0;
  let restoreCalls = 0;

  await page.route("**/api/v1/admin/events/operational", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        removed
          ? []
          : [
              {
                id: 801,
                title: "Зимняя встреча ЭРА",
                status: "registration_open",
                event_date: "2026-12-15",
                event_time: "19:00:00",
                location: "Офис ЭРА",
                registered: 4,
                free: 26,
                points_for_visit: 60,
                show_in_public_listing: true,
              },
            ],
      ),
    }),
  );

  await page.route("**/api/v1/admin/events/801/cancel", async (route) => {
    expect(route.request().method()).toBe("POST");
    cancelCalls += 1;
    removed = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 801, status: "cancelled" }),
    });
  });

  await page.route("**/api/v1/admin/events/801/restore", async (route) => {
    expect(route.request().method()).toBe("POST");
    restoreCalls += 1;
    removed = false;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 801, status: "registration_open" }),
    });
  });

  await enterAdminEventsOperations(page);
  await expect(page.getByText("Зимняя встреча ЭРА")).toBeVisible();

  // Open confirmation sheet and cancel first — nothing should be sent.
  await page.getByTestId("event-remove-801").click();
  await expect(page.getByText("Убрать мероприятие?")).toBeVisible();
  await expect(page.getByTestId("event-remove-registrations-note")).toContainText(
    "Зарегистрировано участников: 4",
  );
  await expect(page.getByTestId("event-remove-registrations-note")).toContainText(
    "Мероприятие отменено",
  );
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  expect(cancelCalls).toBe(0);
  await expect(page.getByText("Зимняя встреча ЭРА")).toBeVisible();

  // Confirm removal — event leaves the list, undo banner remains visible even when the list becomes empty.
  await page.getByTestId("event-remove-801").click();
  await page.getByRole("button", { name: "Убрать мероприятие", exact: true }).click();
  await expect.poll(() => cancelCalls).toBe(1);
  await expect(page.getByTestId("event-remove-801")).toHaveCount(0);
  const undoBanner = page.getByTestId("event-remove-undo-banner");
  await expect(undoBanner).toBeVisible();
  await expect(undoBanner).toContainText("Мероприятие убрано");
  await expect(undoBanner).toContainText("Зимняя встреча ЭРА");

  for (const width of VIEWPORTS) {
    await page.setViewportSize({ width, height: 844 });
    const noOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    );
    expect(noOverflow).toBe(true);
  }

  // Restore via undo — event returns to the operational list.
  await undoBanner.getByRole("button", { name: "Вернуть", exact: true }).click();
  await expect.poll(() => restoreCalls).toBe(1);
  await expect(page.getByTestId("event-remove-undo-banner")).toHaveCount(0);
  await expect(page.getByText("Зимняя встреча ЭРА")).toBeVisible();
  await expect(page.getByTestId("event-remove-801")).toBeVisible();
});

test("non-admin users are denied by server-side cancel and restore endpoints", async ({ request }) => {
  for (const devTelegramId of [900001, 900002]) {
    const authRes = await request.post("/api/v1/miniapp/auth", {
      data: { initData: "", devTelegramId },
    });
    expect(authRes.status()).toBe(200);
    const { token } = (await authRes.json()) as { token: string };

    for (const action of ["cancel", "restore"]) {
      const res = await request.post(`/api/v1/admin/events/1/${action}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(res.status()).toBe(403);
      const body = (await res.json()) as { detail?: string };
      expect(body.detail).toBe("admin_access_required");
    }
  }
});
