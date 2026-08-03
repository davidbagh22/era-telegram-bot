// Minimal typed bridge to the Telegram WebApp JS SDK loaded via the
// <script> tag in index.html (https://core.telegram.org/bots/webapps).
// We only declare the surface this app actually uses.
interface TelegramWebApp {
  initData: string;
  ready: () => void;
  expand: () => void;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string | undefined>;
  onEvent: (eventType: string, callback: () => void) => void;
}

interface TelegramNamespace {
  WebApp?: TelegramWebApp;
}

declare global {
  interface Window {
    Telegram?: TelegramNamespace;
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function getInitData(): string {
  return getTelegramWebApp()?.initData ?? "";
}

export function initTelegramWebApp(): void {
  const webApp = getTelegramWebApp();
  webApp?.ready();
  webApp?.expand();
}

export function getColorScheme(): "light" | "dark" {
  return getTelegramWebApp()?.colorScheme ?? "light";
}
