import { authenticate } from "../api/client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenCache: string | null = null;
let lastScreen: string | null = null;

function normalizedScreen(): string {
  const raw = window.location.hash.replace(/^#\/?/, "").replace(/\/$/, "") || "home";
  const segments = raw.split("/").filter(Boolean).map((segment) => /^\d+$/.test(segment) ? ":id" : segment);
  return segments.join("/") || "home";
}

async function token(): Promise<string> {
  if (tokenCache) return tokenCache;
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  const devTelegramId = raw ? Number(raw) : undefined;
  const auth = await authenticate(getInitData(), devTelegramId);
  tokenCache = auth.token;
  return tokenCache;
}

export async function trackProductEvent(
  name: string,
  metadata: Record<string, string | number | boolean | null | undefined> = {},
): Promise<void> {
  try {
    const bearer = await token();
    const response = await fetch(`${API_BASE_URL}/api/v1/engagement/product-event`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bearer}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name, metadata }),
    });
    if (response.status === 401) tokenCache = null;
  } catch {
    // Analytics must never block participant navigation or actions.
  }
}

function trackScreen(): void {
  const screen = normalizedScreen();
  if (screen === lastScreen) return;
  lastScreen = screen;
  void trackProductEvent("screen_view", { screen });
}

export function installProductAnalytics(): () => void {
  trackScreen();
  window.addEventListener("hashchange", trackScreen);
  window.addEventListener("popstate", trackScreen);
  return () => {
    window.removeEventListener("hashchange", trackScreen);
    window.removeEventListener("popstate", trackScreen);
  };
}
