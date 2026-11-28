import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getTelegramWebApp } from "../telegram/webApp";

const STORAGE_KEY = "era.orbit.liveBackground";

export type MotionPauseReason = "none" | "user" | "reduced-motion" | "inactive";

type MotionPreferenceValue = {
  /** User wants animated ambient (local setting). */
  liveBackground: boolean;
  setLiveBackground: (value: boolean) => void;
  /** OS/browser prefers-reduced-motion: reduce is active. */
  reducedMotion: boolean;
  /** Effective: paused when reduced motion, hidden tab, or user off. */
  motionAllowed: boolean;
  /** Why motion is currently stopped, for explicit UI messaging. */
  pauseReason: MotionPauseReason;
  toggleLiveBackground: () => void;
};

const MotionPreferenceContext = createContext<MotionPreferenceValue | null>(null);

function readStoredPreference(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return true;
    return raw !== "0" && raw !== "false";
  } catch {
    return true;
  }
}

function systemPrefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function MotionPreferenceProvider({ children }: { children: ReactNode }) {
  const [liveBackground, setLiveBackgroundState] = useState(readStoredPreference);
  const [reducedMotion, setReducedMotion] = useState(systemPrefersReducedMotion);
  const [documentVisible, setDocumentVisible] = useState(
    typeof document === "undefined" ? true : document.visibilityState !== "hidden",
  );
  // Start active when the document is visible; Telegram iOS can report `isActive: false`
  // transiently during sheet launch or miss the initial `activated` event before mount.
  // Preloaded/hidden WebViews remain paused via `documentVisible` until revealed.
  const [telegramActive, setTelegramActive] = useState(true);

  const setLiveBackground = useCallback((value: boolean) => {
    setLiveBackgroundState(value);
    if (value && (typeof document === "undefined" || document.visibilityState !== "hidden")) {
      setTelegramActive(true);
    }
    try {
      localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
    } catch {
      /* private mode */
    }
  }, []);

  const toggleLiveBackground = useCallback(() => {
    setLiveBackground(!liveBackground);
  }, [liveBackground, setLiveBackground]);

  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReducedMotion(mq.matches);
    onChange();
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
    // Legacy iOS WebKit fallback.
    mq.addListener?.(onChange);
    return () => mq.removeListener?.(onChange);
  }, []);

  useEffect(() => {
    const webApp = getTelegramWebApp();
    const syncFromHost = () => {
      const visible = document.visibilityState !== "hidden";
      setDocumentVisible(visible);
      if (webApp?.isActive !== false) {
        setTelegramActive(true);
      }
    };
    const onVisibility = () => {
      const visible = document.visibilityState !== "hidden";
      setDocumentVisible(visible);
      // Recover on iOS Telegram WebView if `activated` was missed after returning to foreground.
      if (visible) setTelegramActive(true);
    };
    const onForegroundSignal = () => {
      if (document.visibilityState === "hidden") return;
      setDocumentVisible(true);
      setTelegramActive(true);
    };
    const onUserInteraction = (event: Event) => {
      if (document.visibilityState === "hidden") return;
      const target = event.target;
      if (target instanceof Element && target.closest("[data-motion-control='true']")) {
        if (event.type === "pointerdown") return;
        if (event.type === "keydown") {
          const key = (event as KeyboardEvent).key;
          if (key === "Enter" || key === " ") return;
        }
      }
      setDocumentVisible(true);
      setTelegramActive(true);
    };
    const onDeactivated = () => setTelegramActive(false);
    const onActivated = () => setTelegramActive(true);
    const onViewportChanged = () => {
      if (document.visibilityState !== "hidden" && getTelegramWebApp()?.isActive !== false) {
        setTelegramActive(true);
      }
    };

    syncFromHost();
    const rafId = window.requestAnimationFrame(syncFromHost);

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onForegroundSignal);
    window.addEventListener("pageshow", onForegroundSignal);
    document.addEventListener("pointerdown", onUserInteraction, { passive: true, capture: true });
    document.addEventListener("keydown", onUserInteraction, { passive: true, capture: true });
    try {
      webApp?.onEvent?.("deactivated", onDeactivated);
      webApp?.onEvent?.("activated", onActivated);
      webApp?.onEvent?.("viewportChanged", onViewportChanged);
    } catch {
      /* older clients */
    }
    return () => {
      window.cancelAnimationFrame(rafId);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onForegroundSignal);
      window.removeEventListener("pageshow", onForegroundSignal);
      document.removeEventListener("pointerdown", onUserInteraction, true);
      document.removeEventListener("keydown", onUserInteraction, true);
      webApp?.offEvent?.("deactivated", onDeactivated);
      webApp?.offEvent?.("activated", onActivated);
      webApp?.offEvent?.("viewportChanged", onViewportChanged);
    };
  }, []);

  const motionAllowed = liveBackground && !reducedMotion && documentVisible && telegramActive;
  const pauseReason: MotionPauseReason = reducedMotion
    ? "reduced-motion"
    : !liveBackground
      ? "user"
      : !documentVisible || !telegramActive
        ? "inactive"
        : "none";

  const value = useMemo(
    () => ({
      liveBackground,
      setLiveBackground,
      reducedMotion,
      motionAllowed,
      pauseReason,
      toggleLiveBackground,
    }),
    [liveBackground, setLiveBackground, reducedMotion, motionAllowed, pauseReason, toggleLiveBackground],
  );

  return (
    <MotionPreferenceContext.Provider value={value}>
      {children}
    </MotionPreferenceContext.Provider>
  );
}

export function useMotionPreference(): MotionPreferenceValue {
  const ctx = useContext(MotionPreferenceContext);
  if (!ctx) {
    const reduced = systemPrefersReducedMotion();
    return {
      liveBackground: true,
      setLiveBackground: () => undefined,
      reducedMotion: reduced,
      motionAllowed: !reduced,
      pauseReason: reduced ? "reduced-motion" : "none",
      toggleLiveBackground: () => undefined,
    };
  }
  return ctx;
}
