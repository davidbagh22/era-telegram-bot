import { StatusBanner } from "../components/StatusBanner";

export function BlockedScreen() {
  return (
    <StatusBanner
      title="Доступ ограничен"
      description="Обратитесь к администрации ЭРА через бота, если считаете, что это ошибка."
    />
  );
}
