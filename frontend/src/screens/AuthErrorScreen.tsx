import { StatusBanner } from "../components/StatusBanner";

interface AuthErrorScreenProps {
  code: number;
  detail: string;
}

function messageFor(code: number, detail: string): { title: string; description: string } {
  if (code === 404 && detail === "user_not_registered") {
    return {
      title: "Сначала откройте бота",
      description: "Мы не нашли вашу регистрацию. Откройте бота ЭРА в Telegram и нажмите /start.",
    };
  }
  if (code === 401) {
    return {
      title: "Не удалось подтвердить сессию",
      description: "Закройте Mini App и откройте её снова из бота ЭРА.",
    };
  }
  return {
    title: "Что-то пошло не так",
    description: "Попробуйте открыть ЭРА заново через бота. Если ошибка повторяется, напишите в поддержку.",
  };
}

export function AuthErrorScreen({ code, detail }: AuthErrorScreenProps) {
  const { title, description } = messageFor(code, detail);
  return <StatusBanner title={title} description={description} />;
}
