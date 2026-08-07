import { StatusBanner } from "../components/StatusBanner";

interface PendingScreenProps {
  onRefresh: () => void;
}

export function PendingScreen({ onRefresh }: PendingScreenProps) {
  return (
    <StatusBanner
      title="Заявка на рассмотрении"
      description="Как только администратор примет решение, приложение обновится само — обычно в течение минуты, — и вы получите сообщение от бота. Не хотите ждать — нажмите «Проверить сейчас»."
      actionLabel="Проверить сейчас"
      onAction={onRefresh}
    />
  );
}
