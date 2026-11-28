import { expect, test, type Page } from "@playwright/test";
import type { EventItem } from "../src/types/activity";

/**
 * Regression suite for the decluttered Event Detail screen across all 5 states
 * (not registered, registered future, waitlist, event day, past/completed) and
 * mobile viewports 320–430px. Uses browser-only route overrides on isolated
 * fixtures — no production data or Telegram calls.
 */

const PARTICIPANT_ID = 900001;

function yerevanDateOffset(daysOffset: number): string {
  const shifted = new Date(Date.now() + daysOffset * 24 * 60 * 60 * 1000);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Yerevan",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(shifted);
  const year = parts.find((part) => part.type === "year")?.value ?? "2026";
  const month = parts.find((part) => part.type === "month")?.value ?? "12";
  const day = parts.find((part) => part.type === "day")?.value ?? "19";
  return `${year}-${month}-${day}`;
}

function makeEvent(overrides: Partial<EventItem> = {}): EventItem {
  return {
    id: 777,
    title: "Книжный вечер ЭРА",
    description: "Встреча сообщества и обсуждение книг.",
    short_description: "Встреча сообщества и обсуждение книг.",
    full_description: "Встреча сообщества и обсуждение книг.",
    event_date: yerevanDateOffset(14),
    event_time: "18:00",
    end_time: "20:00",
    location: "Дом ЭРА",
    address: "пр. Баграмяна, 34",
    format: "offline",
    attendance_mode: "offline",
    category: "Культура",
    organizer: "Сообщество ЭРА",
    participant_value: null,
    contact: null,
    chat_url: "https://t.me/era_leaders1",
    registration_url: null,
    points_for_visit: 20,
    project_id: null,
    status: "registration_open",
    display_status: "Регистрация открыта",
    participant_limit: 50,
    registered_count: 1,
    available_places: "49",
    remaining_count: 49,
    registration_status: null,
    waitlist_enabled: true,
    registration_required: true,
    registration_close_at: null,
    can_register: true,
    program: [],
    participant_tasks: [],
    poster_url: null,
    ...overrides,
  };
}

async function mountMockEvent(
  page: Page,
  event: EventItem,
  options: {
    activities?: Array<Record<string, unknown>>;
    attendance?: Record<string, unknown>;
  } = {},
) {
  await page.route("**/api/v1/events?scope=*", async (route) => {
    await route.fulfill({ json: [event] });
  });
  await page.route(`**/api/v1/events/${event.id}/activities`, async (route) => {
    await route.fulfill({ json: options.activities ?? [] });
  });
  await page.route(`**/api/v1/events/${event.id}/attendance`, async (route) => {
    await route.fulfill({
      json: {
        event_id: event.id,
        event_status: event.status,
        eligible: event.registration_status === "registered" || event.registration_status === "will_come" || event.registration_status === "attended",
        confirmation_open: false,
        confirmation_closed: false,
        confirmed: event.registration_status === "attended",
        points_for_visit: event.points_for_visit,
        points_awarded: event.registration_status === "attended",
        proof_status: null,
        can_submit_proof: false,
        ...(options.attendance ?? {}),
      },
    });
  });
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_ID}#/events/${event.id}`);
  await expect(page.getByRole("heading", { name: event.title })).toBeVisible();
}

test("state 1: unregistered future event stays clean with collapsed calendar and primary CTA", async ({ page }) => {
  await mountMockEvent(page, makeEvent());

  await expect(page.getByText("Регистрация открыта")).toBeVisible();
  await expect(page.getByRole("button", { name: "Участвовать", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Добавить в календарь" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Открыть чат" })).toBeVisible();

  await expect(page.getByText("Дополнительных заданий пока нет")).toHaveCount(0);
  await expect(page.getByText("Подтвердить участие")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Google Календарь" })).toHaveCount(0);
  await expect(page.getByText(/На iPhone используйте системное меню/)).toHaveCount(0);
});

test("state 2: registered future event has one status, no empty states, no premature proof, single calendar picker, and quiet cancel", async ({ page }) => {
  const event = makeEvent({
    registration_status: "registered",
    display_status: "Вы зарегистрированы",
    can_register: false,
  });

  // Even if an attendance payload flags can_submit_proof=true early, a future
  // event date must still keep photo proof hidden before the event day.
  await mountMockEvent(page, event, {
    activities: [],
    attendance: { can_submit_proof: true, confirmation_open: false },
  });

  // Single participation status (only in the bottom bar; no duplicate top badge or card).
  await expect(page.getByText("✓ Вы участвуете")).toHaveCount(1);
  await expect(page.getByText("Вы зарегистрированы")).toHaveCount(0);
  await expect(page.getByText(/Подробности и напоминания придут в бот/)).toHaveCount(0);

  // Empty activities and premature attendance confirmation stay hidden.
  await expect(page.getByText("Дополнительных заданий пока нет")).toHaveCount(0);
  await expect(page.getByText("Подтвердить участие")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Прикрепить фото с места/ })).toHaveCount(0);

  // Calendar collapsed into one button; tapping opens Google / Apple / chat options without iPhone essay.
  await expect(page.getByRole("link", { name: "Google Календарь" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Календарь Apple (.ics)" })).toHaveCount(0);
  await expect(page.getByText(/На iPhone используйте системное меню/)).toHaveCount(0);

  let sentToChat = 0;
  await page.route(`**/api/v1/events/${event.id}/calendar/send`, async (route) => {
    sentToChat += 1;
    await route.fulfill({ json: { sent: true } });
  });

  await page.getByRole("button", { name: "Добавить в календарь" }).click();
  const calendarSheet = page.getByRole("dialog", { name: "Добавить в календарь" });
  await expect(calendarSheet).toBeVisible();
  await expect(calendarSheet.getByRole("link", { name: "Google Календарь" })).toBeVisible();
  await expect(calendarSheet.getByRole("button", { name: "Календарь Apple (.ics)" })).toBeVisible();
  await expect(calendarSheet.getByRole("button", { name: "Файл в чат ЭРА" })).toBeVisible();
  await expect(calendarSheet.getByText(/На iPhone используйте системное меню/)).toHaveCount(0);

  await calendarSheet.getByRole("button", { name: "Файл в чат ЭРА" }).click();
  await expect.poll(() => sentToChat).toBe(1);
  await expect(calendarSheet).toHaveCount(0);

  // Compact chat link stays accessible.
  await expect(page.getByRole("link", { name: "Открыть чат" })).toHaveAttribute("href", "https://t.me/era_leaders1");

  // Quiet cancel button opens confirmation dialog rather than cancelling immediately.
  const cancelBtn = page.getByRole("button", { name: "Отказаться", exact: true });
  await expect(cancelBtn).toBeVisible();
  await expect(cancelBtn).toHaveClass(/era-btn-ghost/);
  await cancelBtn.click();
  const confirmDialog = page.getByRole("dialog", { name: "Отказаться от участия?" });
  await expect(confirmDialog).toBeVisible();
  await confirmDialog.getByRole("button", { name: "Остаться" }).click();
  await expect(confirmDialog).toHaveCount(0);
});

test("state 2b: registered event still renders real activities when non-empty", async ({ page }) => {
  await mountMockEvent(
    page,
    makeEvent({
      registration_status: "registered",
      display_status: "Вы зарегистрированы",
      can_register: false,
    }),
    {
      activities: [{
        id: 501,
        title: "Принести любимую книгу",
        description: "Поделитесь цитатой на встрече",
        submission_type: "text",
        points: 15,
        my_status: null,
        submit_deep_link: "https://t.me/ERA_1bot?start=activity_submit_501",
      }],
    },
  );

  await expect(page.getByRole("heading", { name: "Задания мероприятия" })).toBeVisible();
  await expect(page.getByText("Принести любимую книгу")).toBeVisible();
  await expect(page.getByRole("link", { name: "Отправить результат" })).toBeVisible();
});

test("state 3: waitlisted event shows one waitlist status and quiet leave confirmation", async ({ page }) => {
  await mountMockEvent(page, makeEvent({
    registration_status: "waitlist",
    display_status: "Вы в листе ожидания",
    can_register: false,
    remaining_count: 0,
    registered_count: 50,
  }));

  await expect(page.getByText("Вы в листе ожидания")).toHaveCount(1);
  await expect(page.getByText("✓ Вы участвуете")).toHaveCount(0);
  await expect(page.getByText("Подтвердить участие")).toHaveCount(0);

  const leaveBtn = page.getByRole("button", { name: "Покинуть", exact: true });
  await expect(leaveBtn).toHaveClass(/era-btn-ghost/);
  await leaveBtn.click();
  await expect(page.getByRole("dialog", { name: "Покинуть лист ожидания?" })).toBeVisible();
});

test("state 4: event day reveals photo proof and code confirmation when available", async ({ page }) => {
  await mountMockEvent(
    page,
    makeEvent({
      event_date: yerevanDateOffset(0),
      status: "active",
      registration_status: "registered",
      display_status: "Вы зарегистрированы",
      can_register: false,
    }),
    {
      attendance: {
        can_submit_proof: true,
        confirmation_open: true,
      },
    },
  );

  await expect(page.getByText("Идёт сейчас")).toBeVisible();
  await expect(page.getByText("✓ Вы участвуете")).toHaveCount(1);
  await expect(page.getByText("Подтвердить участие")).toBeVisible();
  await expect(page.getByRole("button", { name: "Прикрепить фото с места" })).toBeVisible();
  await expect(page.getByLabel("Код подтверждения участия")).toBeVisible();
});

test("state 4b: overnight active event stays live after midnight in Yerevan", async ({ page }) => {
  await mountMockEvent(
    page,
    makeEvent({
      event_date: yerevanDateOffset(-1),
      event_time: "23:00",
      end_time: "02:00",
      status: "active",
      registration_status: "registered",
      display_status: "Вы зарегистрированы",
      can_register: false,
    }),
    {
      attendance: {
        can_submit_proof: true,
        confirmation_open: false,
      },
    },
  );

  await expect(page.getByText("Идёт сейчас")).toBeVisible();
  await expect(page.getByText("Завершено")).toHaveCount(0);
  await expect(page.getByText("✓ Вы участвуете")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Отказаться", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Прикрепить фото с места" })).toBeVisible();
});

test("state 5: past completed/attended event hides sticky cancel dock and calendar button", async ({ page }) => {
  await mountMockEvent(
    page,
    makeEvent({
      event_date: yerevanDateOffset(-3),
      status: "completed",
      registration_status: "attended",
      display_status: "Завершено",
      can_register: false,
    }),
    {
      attendance: {
        confirmed: true,
        points_awarded: true,
        can_submit_proof: false,
      },
    },
  );

  await expect(page.getByText("Завершено")).toBeVisible();
  await expect(page.getByText("✓ Посещение подтверждено")).toBeVisible();
  await expect(page.getByRole("button", { name: "Отказаться" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Добавить в календарь" })).toHaveCount(0);
  await expect(page.getByText("✓ Вы участвуете")).toHaveCount(0);
});

for (const width of [320, 360, 390, 430]) {
  for (const scale of [1, 1.5]) {
    test(`decluttered registered event detail fits ${width}px at ${Math.round(scale * 100)}% font scale`, async ({ page }) => {
      await page.setViewportSize({ width, height: 780 });
      await mountMockEvent(
        page,
        makeEvent({
          title: "Сверхдлинное_название_мероприятия_ЭРА для проверки переноса на узком экране",
          registration_status: "registered",
          display_status: "Вы зарегистрированы",
          can_register: false,
        }),
      );
      if (scale !== 1) {
        await page.addStyleTag({ content: `html { font-size: ${scale * 100}% !important; }` });
      }
      await page.waitForTimeout(150);

      const overflow = await page.evaluate(() => {
        const root = document.scrollingElement ?? document.documentElement;
        return { scrollWidth: root.scrollWidth, innerWidth: window.innerWidth };
      });
      expect(overflow.scrollWidth, `overflow at ${width}/${scale}`).toBeLessThanOrEqual(overflow.innerWidth);

      const offenders = await page.evaluate(() => {
        const vw = window.innerWidth;
        const bad: string[] = [];
        for (const el of document.querySelectorAll<HTMLElement>("button, a[href], h2, h3")) {
          const rect = el.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) continue;
          if (el.closest(".era-sr-only, [aria-hidden='true'], [hidden]")) continue;
          if (rect.left < -1 || rect.right > vw + 1) {
            bad.push(`${el.tagName}[${(el.innerText || "").trim().slice(0, 30)}] ${Math.round(rect.left)}..${Math.round(rect.right)}/${vw}`);
          }
        }
        return bad;
      });
      expect(offenders, `controls outside viewport at ${width}/${scale}`).toEqual([]);

      await page.getByRole("button", { name: "Добавить в календарь" }).click();
      const sheet = page.getByRole("dialog", { name: "Добавить в календарь" });
      await expect(sheet).toBeVisible();
      const box = await sheet.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    });
  }
}
