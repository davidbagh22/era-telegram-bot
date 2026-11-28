import { expect, test } from "@playwright/test";

const VIEWPORTS = [320, 390, 430] as const;

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-28T08:00:00Z"));
});

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto("/app/?devTelegramId=900003");
  await page
    .getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Я", exact: true })
    .click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Пульт руководителя", { exact: true })).toBeVisible();
}

async function assertNoHorizontalOverflow(page: import("@playwright/test").Page) {
  const ok = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  expect(ok).toBe(true);
}

test("admin Работа → Задания collapses boilerplate, drops seconds, separates expired tasks across 320–430px", async ({ page }) => {
  await page.route("**/api/v1/leader/open-tasks", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 501,
          title: "Запиши видео «Почему я с ЭРА»",
          description:
            "Запиши короткое вертикальное видео на 30–60 секунд про свой опыт в ЭРА.\n\n" +
            "Выполните задание, затем нажмите «Отправить результат» в боте. Если материал уже отправлен в @era_leaders, приложите ссылку или скриншот отправки. Нажмите «Подтвердить отправку». Баллы начисляются один раз после проверки администратором.",
          deadline: "2026-12-20T12:41:53Z",
          points: 50,
          max_participants: 20,
          applications: [],
          deliveries: [],
        },
        {
          id: 502,
          title: "Старое просроченное задание",
          description: "Короткое описание задачи, срок которой уже прошёл.",
          deadline: "2026-11-13T12:41:53Z",
          points: 40,
          max_participants: 10,
          applications: [],
          deliveries: [],
        },
      ]),
    }),
  );

  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Работа", exact: true }).click();
  await page.getByRole("button", { name: /Задания.*Создание задач/ }).click();
  await page.getByRole("button", { name: /Создать задание/ }).click();

  const activeSection = page.getByTestId("active-tasks-section");
  await expect(activeSection.getByText("Запиши видео «Почему я с ЭРА»")).toBeVisible();
  await expect(activeSection.getByText("Открыто", { exact: true })).toBeVisible();
  // No raw seconds in formatted deadline.
  await expect(activeSection).not.toContainText(":53");
  // Boilerplate paragraph is collapsed until «Подробнее» is clicked.
  await expect(activeSection).not.toContainText("Баллы начисляются один раз");
  await activeSection.getByRole("button", { name: "Подробнее", exact: true }).click();
  await expect(activeSection).toContainText("Баллы начисляются один раз");
  await activeSection.getByRole("button", { name: "Свернуть", exact: true }).click();
  await expect(activeSection).not.toContainText("Баллы начисляются один раз");

  // Expired task is separated from active tasks behind a toggle and marked «Срок прошёл».
  const expiredSection = page.getByTestId("expired-tasks-section");
  await expect(expiredSection.getByRole("button", { name: /Срок прошёл · 1/ })).toBeVisible();
  await expect(expiredSection.getByText("Старое просроченное задание")).toHaveCount(0);
  await expiredSection.getByRole("button", { name: /Срок прошёл · 1/ }).click();
  await expect(expiredSection.getByText("Старое просроченное задание")).toBeVisible();
  await expect(expiredSection.getByText("Срок прошёл", { exact: true })).toBeVisible();
  await expect(expiredSection).not.toContainText(":53");

  for (const width of VIEWPORTS) {
    await page.setViewportSize({ width, height: 844 });
    await assertNoHorizontalOverflow(page);
  }
});

test("admin Работа → Мероприятия formats date cleanly, keeps status pill single-line, and aligns action grid across 320–430px", async ({ page }) => {
  await page.route("**/api/v1/admin/events/operational", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 601,
          title: "Празднование 1-летия ЭРА",
          status: "registration_open",
          event_date: "2026-12-12",
          event_time: "18:00:00",
          location: "Ресторан «Таверна Ереван», зал Арцах",
          registered: 8,
          free: 42,
          points_for_visit: 100,
          show_in_public_listing: true,
        },
        {
          id: 602,
          title: "Еженедельное собрание активистов ЭРА",
          status: "registration_open",
          event_date: "2026-11-29",
          event_time: "14:00:00",
          location: "Офис ЭРА",
          registered: 5,
          free: 20,
          points_for_visit: 50,
          show_in_public_listing: false,
        },
      ]),
    }),
  );

  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Работа", exact: true }).click();
  await page.getByRole("button", { name: /^Мероприятия.*Создание/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();

  await expect(page.getByText("12 декабря, 18:00")).toBeVisible();
  await expect(page.getByText("29 ноября, 14:00")).toBeVisible();
  await expect(page.getByText("2026-12-12")).toHaveCount(0);
  await expect(page.getByText("18:00:00")).toHaveCount(0);

  for (const width of VIEWPORTS) {
    await page.setViewportSize({ width, height: 844 });
    await assertNoHorizontalOverflow(page);

    const pill = page.getByText("Регистрация открыта", { exact: true }).first();
    const title = page.getByText("Празднование 1-летия ЭРА", { exact: true });
    const pillBox = await pill.boundingBox();
    const titleBox = await title.boundingBox();
    expect(pillBox).not.toBeNull();
    expect(titleBox).not.toBeNull();
    // Single-line pill above title (never wraps to two lines or crowds title).
    expect(pillBox!.height).toBeLessThanOrEqual(32);
    expect(pillBox!.y + pillBox!.height).toBeLessThanOrEqual(titleBox!.y + 2);

    // Full-width action buttons align cleanly to the exact same left edge & width.
    const actions1 = page.getByTestId("event-actions-601");
    const participantsBtn1 = await actions1.getByRole("button", { name: "Участники · 8" }).boundingBox();
    const hideBtn1 = await actions1.getByRole("button", { name: "Скрыть из общей афиши" }).boundingBox();
    const editBtn1 = await actions1.getByRole("button", { name: "Редактировать мероприятие" }).boundingBox();
    const posterBtn1 = await actions1.getByRole("button", { name: "Изменить афишу" }).boundingBox();
    const removeBtn1 = await actions1.getByRole("button", { name: "Убрать", exact: true }).boundingBox();
    expect(participantsBtn1).not.toBeNull();
    expect(hideBtn1).not.toBeNull();
    expect(editBtn1).not.toBeNull();
    expect(posterBtn1).not.toBeNull();
    expect(removeBtn1).not.toBeNull();

    expect(Math.abs(participantsBtn1!.x - hideBtn1!.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(participantsBtn1!.width - hideBtn1!.width)).toBeLessThanOrEqual(1);
    expect(Math.abs(participantsBtn1!.x - removeBtn1!.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(participantsBtn1!.width - removeBtn1!.width)).toBeLessThanOrEqual(1);
    expect(Math.abs(participantsBtn1!.x - editBtn1!.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(editBtn1!.width - posterBtn1!.width)).toBeLessThanOrEqual(2);

    // Second card («Вернуть в общую афишу») also shares the exact left alignment.
    const actions2 = page.getByTestId("event-actions-602");
    const participantsBtn2 = await actions2.getByRole("button", { name: "Участники · 5" }).boundingBox();
    const showBtn2 = await actions2.getByRole("button", { name: "Вернуть в общую афишу" }).boundingBox();
    expect(Math.abs(participantsBtn2!.x - showBtn2!.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(participantsBtn2!.width - showBtn2!.width)).toBeLessThanOrEqual(1);
  }
});

test("admin Работа → Мероприятия → Участники renders even filter chips and clean rows across 320–430px", async ({ page }) => {
  await page.route("**/api/v1/admin/events/operational", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 701,
          title: "Празднование 1-летия ЭРА",
          status: "published",
          event_date: "2026-12-12",
          event_time: "18:00:00",
          location: "Ресторан «Таверна Ереван»",
          registered: 2,
          free: 48,
          points_for_visit: 100,
          show_in_public_listing: true,
        },
      ]),
    }),
  );
  await page.route("**/api/v1/admin/events/701/participants", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          registration_id: 1,
          user_id: 10,
          participant_name: "Aneta Martirosyan",
          organization: "@aneet.m",
          phone: "+37477554442",
          status: "registered",
          registered_at: "2026-11-27T14:20:00Z",
        },
        {
          registration_id: 2,
          user_id: 11,
          participant_name: "Artyom Grigoryan",
          organization: "РАУ · активист",
          phone: "+37499112233",
          status: "attended",
          registered_at: "2026-11-26T10:05:00Z",
        },
      ]),
    }),
  );
  await page.route("**/api/v1/admin/events/701/lifecycle", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        event_id: 701,
        status: "published",
        has_active_code: false,
        checkin_code: null,
        expires_at: null,
        confirmed_count: 1,
      }),
    }),
  );

  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Работа", exact: true }).click();
  await page.getByRole("button", { name: /^Мероприятия.*Создание/ }).click();
  await page.getByRole("button", { name: /Участники и посещаемость/ }).click();
  await page.getByRole("button", { name: "Участники · 2" }).click();

  await expect(page.getByText("Aneta Martirosyan")).toBeVisible();
  await expect(page.getByText("@aneet.m · +37477554442")).toBeVisible();

  for (const width of VIEWPORTS) {
    await page.setViewportSize({ width, height: 844 });
    await assertNoHorizontalOverflow(page);

    // Filter chips form a clean equal-width 2-column grid.
    const chips = page.getByTestId("participant-filter-chips").locator("button");
    await expect(chips).toHaveCount(4);
    const chip0 = await chips.nth(0).boundingBox();
    const chip1 = await chips.nth(1).boundingBox();
    const chip2 = await chips.nth(2).boundingBox();
    expect(chip0 && chip1 && chip2).toBeTruthy();
    expect(Math.abs(chip0!.width - chip1!.width)).toBeLessThanOrEqual(2);
    expect(Math.abs(chip0!.x - chip2!.x)).toBeLessThanOrEqual(1);

    // Participant row: single-line status badge, contact line stacked cleanly below name.
    const row = page.getByTestId("participant-row-1");
    const nameBox = await row.getByText("Aneta Martirosyan").boundingBox();
    const badgeBox = await row.getByText("Ждёт подтверждения", { exact: true }).boundingBox();
    const contactBox = await row.getByText("@aneet.m · +37477554442").boundingBox();
    expect(nameBox && badgeBox && contactBox).toBeTruthy();
    expect(badgeBox!.height).toBeLessThanOrEqual(32);
    expect(contactBox!.y).toBeGreaterThanOrEqual(nameBox!.y + nameBox!.height - 1);
    // Contact line spans cleanly (not crushed into a tiny middle column).
    expect(contactBox!.width).toBeGreaterThan(150);
  }
});
