const telegram = window.Telegram?.WebApp;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
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
    throw new ApiError(response.status, data.detail || "Не удалось выполнить запрос.");
  }
  return data as T;
}

export const haptic = {
  tap: () => telegram?.HapticFeedback?.impactOccurred("light"),
  success: () => telegram?.HapticFeedback?.notificationOccurred("success"),
  error: () => telegram?.HapticFeedback?.notificationOccurred("error")
};

export function initializeTelegram(): void {
  telegram?.ready();
  telegram?.expand();
  telegram?.enableClosingConfirmation();
  telegram?.disableVerticalSwipes?.();
}
