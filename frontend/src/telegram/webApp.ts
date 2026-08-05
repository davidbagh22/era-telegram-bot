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
  applyTelegramTheme();
  webApp?.onEvent("themeChanged", applyTelegramTheme);
}

export function getColorScheme(): "light" | "dark" {
  return getTelegramWebApp()?.colorScheme ?? "light";
}

// Mirrors Telegram's own light/dark theme onto the document so
// tokens.css's `[data-theme="dark"]` overrides apply — without this the
// Mini App stays light-only even when opened from a dark-themed Telegram
// client. Safe to call outside Telegram (falls back to "light", matching
// the existing browser-preview default).
export function applyTelegramTheme(): void {
  document.documentElement.dataset.theme = getColorScheme();
}
