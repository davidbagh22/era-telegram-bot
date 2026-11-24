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

type MotionPreferenceValue = {
  /** User wants animated ambient (local setting). */
  liveBackground: boolean;
  setLiveBackground: (value: boolean) => void;
  /** Effective: paused when reduced motion, hidden tab, or user off. */
  motionAllowed: boolean;
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
  const [telegramActive, setTelegramActive] = useState(() => getTelegramWebApp()?.isActive !== false);

  const setLiveBackground = useCallback((value: boolean) => {
    setLiveBackgroundState(value);
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
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  useEffect(() => {
    const onVisibility = () => setDocumentVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", onVisibility);
    const webApp = getTelegramWebApp();
    const onDeactivated = () => setTelegramActive(false);
    const onActivated = () => setTelegramActive(true);
    try {
      webApp?.onEvent?.("deactivated", onDeactivated);
      webApp?.onEvent?.("activated", onActivated);
    } catch {
      /* older clients */
    }
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      webApp?.offEvent?.("deactivated", onDeactivated);
      webApp?.offEvent?.("activated", onActivated);
    };
  }, []);

  const motionAllowed = liveBackground && !reducedMotion && documentVisible && telegramActive;

  const value = useMemo(
    () => ({ liveBackground, setLiveBackground, motionAllowed, toggleLiveBackground }),
    [liveBackground, setLiveBackground, motionAllowed, toggleLiveBackground],
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
    return {
      liveBackground: true,
      setLiveBackground: () => undefined,
      motionAllowed: !systemPrefersReducedMotion(),
      toggleLiveBackground: () => undefined,
    };
  }
  return ctx;
}
