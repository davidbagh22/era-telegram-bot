// Minimal typed bridge to the Telegram WebApp JS SDK loaded via the
// <script> tag in index.html. ERA intentionally keeps its own light,
// signal-gradient visual system instead of inheriting Telegram's palette.
interface TelegramHapticFeedback {
  impactOccurred?: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
  notificationOccurred?: (type: "error" | "success" | "warning") => void;
  selectionChanged?: () => void;
}

interface TelegramWebApp {
  initData: string;
  ready: () => void;
  expand: () => void;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string | undefined>;
  onEvent: (eventType: string, callback: () => void) => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  setBottomBarColor?: (color: string) => void;
  HapticFeedback?: TelegramHapticFeedback;
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
  applyTelegramTheme();
  webApp?.ready();
  webApp?.expand();
  // Re-apply ERA chrome if Telegram itself changes theme while the Mini App is open.
  webApp?.onEvent("themeChanged", applyTelegramTheme);
}

export function getColorScheme(): "light" | "dark" {
  return "light";
}

export function applyTelegramTheme(): void {
  document.documentElement.dataset.theme = "light";
  document.documentElement.style.backgroundColor = "#F7F7FA";
  document.body?.style.setProperty("background-color", "#F7F7FA");

  const webApp = getTelegramWebApp();
  // Keep Telegram's surrounding Mini App chrome visually continuous with ERA.
  try { webApp?.setHeaderColor?.("#F7F7FA"); } catch { /* older clients */ }
  try { webApp?.setBackgroundColor?.("#F7F7FA"); } catch { /* older clients */ }
  try { webApp?.setBottomBarColor?.("#F7F7FA"); } catch { /* older clients */ }
}

export function selectionHaptic(): void {
  try { getTelegramWebApp()?.HapticFeedback?.selectionChanged?.(); } catch { /* unsupported client */ }
}

export function successHaptic(): void {
  try { getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("success"); } catch { /* unsupported client */ }
}
