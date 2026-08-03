import { StatusBanner } from "../components/StatusBanner";

export function PendingScreen() {
  return (
    <StatusBanner
      title="Заявка на рассмотрении"
      description="Как только администратор примет решение, вы получите сообщение от бота. Откройте ЭРА снова после этого."
    />
  );
}
