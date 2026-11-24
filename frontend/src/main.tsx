import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { installProductAnalytics } from "./analytics/productAnalytics";
import { App } from "./app/App";
import { ToastProvider } from "./components/Toast";
import { MotionPreferenceProvider } from "./motion/MotionPreference";
import { AppShell } from "./layouts/AppShell";
import { applyTelegramTheme, initTelegramBackNavigation } from "./telegram/webApp";
import "./theme/tokens.css";
import "./theme/motion.css";
import "./theme/layout-safety.css";

// AURA×ORBIT dark chrome — apply before first paint.
applyTelegramTheme();
initTelegramBackNavigation();
installProductAnalytics();

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element not found");
}

createRoot(container).render(
  <StrictMode>
    <MotionPreferenceProvider>
      <ToastProvider>
        <AppShell><App /></AppShell>
      </ToastProvider>
    </MotionPreferenceProvider>
  </StrictMode>,
);
