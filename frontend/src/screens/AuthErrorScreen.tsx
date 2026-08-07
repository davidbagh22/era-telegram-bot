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
    <StatusBanner title={title} description={description} actionLabel="Обновить" onAction={onRetry} />
  );
}
