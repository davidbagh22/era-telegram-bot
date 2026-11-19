// Minimal typed bridge to the Telegram WebApp JS SDK loaded via the
// <script> tag in index.html. ERA AURA×ORBIT uses a dark blue glass chrome
// aligned with Telegram Mini App header/background/bottom bar.
interface TelegramHapticFeedback {
  impactOccurred?: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
  notificationOccurred?: (type: "error" | "success" | "warning") => void;
  selectionChanged?: () => void;
}

interface TelegramBackButton {
  isVisible?: boolean;
  show?: () => void;
  hide?: () => void;
  onClick?: (callback: () => void) => void;
  offClick?: (callback: () => void) => void;
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
  openTelegramLink?: (url: string) => void;
  openLink?: (url: string) => void;
  close?: () => void;
  shareMessage?: (msgId: string, callback?: (success: boolean) => void) => void;
  BackButton?: TelegramBackButton;
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
  bindPrimaryButtonHaptics();
}

export function getColorScheme(): "light" | "dark" {
  return "dark";
}

const AURA_BG = "#070b18";
const AURA_BAR = "#0a1223";

export function applyTelegramTheme(): void {
  document.documentElement.dataset.theme = "aura";
  document.documentElement.style.backgroundColor = AURA_BG;
  document.body?.style.setProperty("background-color", AURA_BG);

  const webApp = getTelegramWebApp();
  // Keep Telegram's surrounding Mini App chrome visually continuous with AURA.
  try { webApp?.setHeaderColor?.(AURA_BG); } catch { /* older clients */ }
  try { webApp?.setBackgroundColor?.(AURA_BG); } catch { /* older clients */ }
  try { webApp?.setBottomBarColor?.(AURA_BAR); } catch { /* older clients */ }
}

function currentHashRoute(): string {
  return window.location.hash.replace(/^#\/?/, "").replace(/^\//, "").replace(/\/$/, "");
}

function parentRoute(route: string): string | null {
  const roots = new Set([
    "",
    "home",
    "projects",
    "participation",
    "opportunities",
    "profile",
    "admin",
    "leader",
    "community",
    "people",
    "teams",
    "ideas",
    "discover",
  ]);
  if (roots.has(route)) return null;

  if (route === "development" || route === "progress") return "home";
  if (route.startsWith("development/")) return "development";
  if (route === "era-pro") return "opportunities";

  if (/^admin\/events\/\d+$/.test(route) || /^admin\/projects\/\d+$/.test(route)) return "admin";
  if (route.startsWith("admin/")) return "admin";

  if (/^projects\/\d+$/.test(route)) return "projects";
  if (/^events\/\d+$/.test(route) || route === "events") return "participation";
  if (/^tasks\/\d+$/.test(route)) return "tasks";
  if (route === "tasks" || route === "calendar" || route === "history") return "home";

  if (/^users\/\d+$/.test(route)) return "people";
  if (/^(opportunities|auctions|rewards|surveys|media)\/\d+$/.test(route)) return "opportunities";
  if (["auctions", "rewards", "surveys", "media", "leaderboard"].includes(route)) return "opportunities";
  if (["media/guide", "media/era", "media/ksoors"].includes(route)) return "media";

  if (route.startsWith("leader/")) return "leader";
  return "home";
}

/**
 * Keep Telegram's native BackButton deterministic for every hash-routed child screen.
 * We intentionally do not depend on WebView browser history: Telegram can inject its
 * own entries, which made the arrow appear only sometimes on iOS/Android.
 */
export function initTelegramBackNavigation(): () => void {
  const backButton = getTelegramWebApp()?.BackButton;
  if (!backButton?.show || !backButton.hide || !backButton.onClick) return () => {};

  const sync = () => {
    const parent = parentRoute(currentHashRoute());
    try {
      if (parent) backButton.show?.();
      else backButton.hide?.();
    } catch {
      // Older Telegram clients may expose a partial BackButton implementation.
    }
  };

  const goBack = () => {
    const parent = parentRoute(currentHashRoute());
    if (!parent) {
      sync();
      return;
    }
    window.location.hash = `#/${parent}`;
  };

  backButton.onClick(goBack);
  window.addEventListener("hashchange", sync);
  sync();

  return () => {
    window.removeEventListener("hashchange", sync);
    try { backButton.offClick?.(goBack); } catch { /* unsupported client */ }
    try { backButton.hide?.(); } catch { /* unsupported client */ }
  };
}

export function openTelegramShare(url: string, text: string): boolean {
  const webApp = getTelegramWebApp();
  if (!webApp?.openTelegramLink) return false;
  const shareUrl = new URL("https://t.me/share/url");
  shareUrl.searchParams.set("url", url);
  shareUrl.searchParams.set("text", text);
  try {
    webApp.openTelegramLink(shareUrl.toString());
    return true;
  } catch {
    return false;
  }
}

export function selectionHaptic(): void {
  try { getTelegramWebApp()?.HapticFeedback?.selectionChanged?.(); } catch { /* unsupported client */ }
}

export function impactHaptic(style: "light" | "medium" | "heavy" = "light"): void {
  try { getTelegramWebApp()?.HapticFeedback?.impactOccurred?.(style); } catch { /* unsupported client */ }
}

export function successHaptic(): void {
  try { getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("success"); } catch { /* unsupported client */ }
}

let primaryHapticsBound = false;

/** Light tap feedback on primary/signal CTAs without wiring every screen. */
export function bindPrimaryButtonHaptics(): void {
  if (primaryHapticsBound || typeof document === "undefined") return;
  primaryHapticsBound = true;
  document.addEventListener(
    "click",
    (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const control = target.closest(".era-btn-primary, .era-btn-signal");
      if (!control || (control instanceof HTMLButtonElement && control.disabled)) return;
      impactHaptic("light");
    },
    true,
  );
}
