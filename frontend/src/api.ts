const telegram = window.Telegram?.WebApp;
let telegramInitialized = false;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : ""
        )
        .filter(Boolean);
      if (messages.length) return messages.join(". ");
    }
  }
  if (status === 422) return "Проверьте обязательные поля анкеты.";
  if (status >= 500) return "Сервис временно не смог сохранить данные. Попробуйте ещё раз.";
  return "Не удалось выполнить запрос.";
}

function headers(body?: unknown): HeadersInit {
  const result: Record<string, string> = {};
  if (body !== undefined) result["Content-Type"] = "application/json";
  if (telegram?.initData) {
    result["X-Telegram-Init-Data"] = telegram.initData;
  } else if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
    result["X-Dev-Telegram-Id"] = "1593868942";
  }
  return result;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...headers(options.body),
      ...(options.headers || {})
    }
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data, response.status));
  }
  return data as T;
}

export const haptic = {
  tap: () => telegram?.HapticFeedback?.impactOccurred("light"),
  success: () => telegram?.HapticFeedback?.notificationOccurred("success"),
  error: () => telegram?.HapticFeedback?.notificationOccurred("error")
};

export function initializeTelegram(): void {
  if (telegramInitialized) return;
  telegramInitialized = true;

  const updateViewport = () => {
    const visualHeight = window.visualViewport?.height;
    const height =
      document.body.classList.contains("keyboard-open") && visualHeight
        ? visualHeight
        : telegram?.viewportStableHeight || visualHeight || window.innerHeight;
    document.documentElement.style.setProperty("--app-height", `${Math.round(height)}px`);
  };

  telegram?.ready();
  telegram?.expand();
  telegram?.enableClosingConfirmation();
  telegram?.disableVerticalSwipes?.();
  telegram?.onEvent("viewportChanged", updateViewport);
  window.visualViewport?.addEventListener("resize", updateViewport);
  updateViewport();

  document.addEventListener("focusin", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) return;
    document.body.classList.add("keyboard-open");
    window.setTimeout(() => target.scrollIntoView({ block: "center", behavior: "smooth" }), 180);
  });
  document.addEventListener("focusout", () => {
    window.setTimeout(() => {
      const active = document.activeElement;
      if (!(active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement || active instanceof HTMLSelectElement)) {
        document.body.classList.remove("keyboard-open");
        updateViewport();
      }
    }, 120);
  });
}
