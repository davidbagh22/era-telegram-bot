import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { applyTelegramTheme } from "./telegram/webApp";
import "./theme/tokens.css";

// Set light/dark before the first paint so there is no flash of the wrong
// theme; initTelegramWebApp() (called from useAuth) re-applies this once
// the Telegram WebApp SDK is confirmed ready and keeps it live via
// themeChanged, but the app can render before that effect runs.
applyTelegramTheme();

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element not found");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
