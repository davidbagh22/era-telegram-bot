interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: {
      id: number;
      first_name: string;
      last_name?: string;
      username?: string;
    };
  };
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  viewportHeight: number;
  viewportStableHeight: number;
  ready(): void;
  expand(): void;
  close(): void;
  enableClosingConfirmation(): void;
  disableVerticalSwipes?(): void;
  onEvent(eventType: "viewportChanged", callback: () => void): void;
  offEvent(eventType: "viewportChanged", callback: () => void): void;
  HapticFeedback?: {
    impactOccurred(style: "light" | "medium" | "heavy"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
    selectionChanged(): void;
  };
  openTelegramLink(url: string): void;
}

interface Window {
  Telegram?: {
    WebApp: TelegramWebApp;
  };
}
