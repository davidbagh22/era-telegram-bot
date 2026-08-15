import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { ToastProvider } from "./components/Toast";
import { applyTelegramTheme } from "./telegram/webApp";
import "./theme/tokens.css";
import "./theme/motion.css";
import "./theme/layout-safety.css";

// ERA uses one intentional dark product identity inside Telegram.
// Apply it before first paint to avoid a light-theme flash.
applyTelegramTheme();

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
