import type { Page } from "@playwright/test";

export interface TelegramStubOptions {
  safeArea?: { top: number; bottom: number; left?: number; right?: number };
  initialActive?: boolean;
}

/** Minimal Telegram WebApp double with an event bus the test can fire. Never touches the network. */
export async function installTelegramStub(page: Page, options: TelegramStubOptions = {}) {
  await page.route("https://telegram.org/**", (route) => route.abort());
  await page.addInitScript((opts) => {
    const handlers: Record<string, Array<() => void>> = {};
    const safe = opts.safeArea
      ? { top: opts.safeArea.top, bottom: opts.safeArea.bottom, left: opts.safeArea.left ?? 0, right: opts.safeArea.right ?? 0 }
      : undefined;
    const webApp = {
      initData: "",
      isActive: opts.initialActive ?? true,
      colorScheme: "light",
      themeParams: {},
      ready() {},
      expand() {},
      onEvent(name: string, cb: () => void) { (handlers[name] ||= []).push(cb); },
      offEvent(name: string, cb: () => void) { handlers[name] = (handlers[name] || []).filter((item) => item !== cb); },
      setHeaderColor() {}, setBackgroundColor() {}, setBottomBarColor() {},
      safeAreaInset: safe,
      contentSafeAreaInset: safe ? { top: 0, bottom: 0, left: 0, right: 0 } : undefined,
    };
    (window as unknown as { Telegram: unknown }).Telegram = { WebApp: webApp };
    (window as unknown as { __tgEmit: (name: string, patch?: Record<string, unknown>) => void }).__tgEmit = (name, patch) => {
      if (patch) Object.assign(webApp, patch);
      (handlers[name] || []).slice().forEach((cb) => cb());
    };
  }, options);
}

/** Simulate Telegram backgrounding / re-opening the WebView. */
export async function setAppActive(page: Page, active: boolean) {
  await page.evaluate((isActive) => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => (isActive ? "visible" : "hidden") });
    Object.defineProperty(document, "hidden", { configurable: true, get: () => !isActive });
    const emit = (window as unknown as { __tgEmit: (name: string, patch?: Record<string, unknown>) => void }).__tgEmit;
    emit(isActive ? "activated" : "deactivated", { isActive });
    document.dispatchEvent(new Event("visibilitychange"));
  }, active);
}
