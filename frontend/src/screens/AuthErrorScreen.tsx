import { StatusBanner } from "../components/StatusBanner";

interface AuthErrorScreenProps {
  code: number;
  detail: string;
  onRetry: () => void;
}

function messageFor(code: number, detail: string): { title: string; description: string } {
  if (code === 404 && detail === "user_not_registered") {
    return {
      title: "Сначала откройте бота",
      description:
        "Мы не нашли вашу регистрацию. Откройте бота ЭРА в Telegram, нажмите /start и завершите регистрацию — затем вернитесь сюда и нажмите «Обновить».",
    };
  }
  if (code === 401) {
    return {
      title: "Не удалось подтвердить сессию",
      description: "Сессия устарела. Нажмите «Обновить» — обычно этого достаточно, закрывать приложение не нужно.",
    };
  }
  return {
    title: "Что-то пошло не так",
    description: "Нажмите «Обновить». Если ошибка повторяется, откройте ЭРА заново через бота или напишите в поддержку.",
  };
}

export function AuthErrorScreen({ code, detail, onRetry }: AuthErrorScreenProps) {
  const { title, description } = messageFor(code, detail);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <StatusBanner title={title} description={description} actionLabel="Обновить" onAction={onRetry} />
      {/* The generic messages above intentionally don't distinguish *why*
       * the session failed (expired vs. a signature mismatch vs. a
       * malformed payload all read as "session expired" to a participant —
       * see messageFor above). This exact code is what actually tells that
       * story: if it says the same thing on every retry across every entry
       * point (menu button, notification links, group-chat buttons), that
       * points at a server-side misconfiguration rather than a genuinely
       * stale session, and this line is what makes that diagnosable from a
       * screenshot instead of needing server log access. */}
      <p style={{ margin: 0, textAlign: "center", fontSize: "var(--era-text-xs)", color: "var(--era-text-muted)" }}>
        Код: {code} · {detail}
      </p>
    </div>
  );
}
