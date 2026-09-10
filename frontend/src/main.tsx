import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { installProductAnalytics } from "./analytics/productAnalytics";
import { App } from "./app/App";
import { ToastProvider } from "./components/Toast";
import { initTelegramBackNavigation, initTelegramWebApp } from "./telegram/webApp";
import "./theme/tokens.css";
import "./theme/motion.css";
import "./theme/layout-safety.css";

// ERA uses one intentional light/signal product identity inside Telegram.
// Initialize Telegram before first paint so theme, viewport and native back
// navigation stay in sync with the current Mini App screen.
initTelegramWebApp();
initTelegramBackNavigation();
installProductAnalytics();

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element not found");
}

createRoot(container).render(
  <StrictMode>
    <ToastProvider>
      <App />
    </ToastProvider>
  </StrictMode>,
);
