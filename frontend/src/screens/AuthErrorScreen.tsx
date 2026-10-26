import { StatusBanner } from "../components/StatusBanner";
import { getTelegramWebApp } from "../telegram/webApp";

function openBotLogin(): void {
  const url = "https://t.me/ERA_1bot?start=miniapp";
  const webApp = getTelegramWebApp();
  if (webApp?.openTelegramLink) {
    try {
      webApp.openTelegramLink(url);
      webApp.close?.();
      return;
    } catch { /* fall back to Telegram's HTTPS deep link */ }
  }
  window.location.assign(url);
}

interface AuthErrorScreenProps {
  code: number;
  detail: string;
  onRetry: () => void;
}

function messageFor(code: number, detail: string): { title: string; description: string } {
  if (code === 401 && detail === "empty_init_data") {
    return {
      title: "Войдите через бота ЭРА",
      description: "Telegram открыл приложение без данных для входа. Нажмите «Войти через бота», затем «Открыть ЭРА» в сообщении бота. Удалять переписку и проходить регистрацию заново не нужно.",
    };
  }
  if (code === 404 && detail === "user_not_registered") {
    return {
      title: "Сначала откройте бота",
      description:
        "Мы не нашли вашу регистрацию. Нажмите «Войти через бота», завершите регистрацию и откройте приложение кнопкой в сообщении бота.",
    };
  }
  if (code === 401) {
    return {
      title: "Не удалось подтвердить сессию",
      description: "Не удалось подтвердить вход. Нажмите «Войти через бота», чтобы открыть приложение с новой сессией Telegram.",
    };
  }
  return {
    title: "Что-то пошло не так",
    description: "Нажмите «Обновить». Если ошибка повторяется, откройте ЭРА заново через бота или напишите в поддержку.",
  };
}

export function AuthErrorScreen({ code, detail, onRetry }: AuthErrorScreenProps) {
  const { title, description } = messageFor(code, detail);
  const needsLogin = code === 401 || (code === 404 && detail === "user_not_registered");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <StatusBanner title={title} description={description} actionLabel={needsLogin ? "Войти через бота" : "Обновить"} onAction={needsLogin ? openBotLogin : onRetry} />
      <p style={{ margin: 0, textAlign: "center", fontSize: "var(--era-text-xs)", color: "var(--era-text-muted)" }}>
        Код: {code} · {detail}
      </p>
    </div>
  );
}
