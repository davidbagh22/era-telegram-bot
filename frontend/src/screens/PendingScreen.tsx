import { StatusBanner } from "../components/StatusBanner";

interface PendingScreenProps {
  onRefresh: () => void;
  status?: string;
}

export function PendingScreen({ onRefresh, status = "pending" }: PendingScreenProps) {
  const needsInfo = status === "needs_info";
  const openBot = () => {
    const url = "https://t.me/ERA_1bot";
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram.WebApp.openTelegramLink(url);
      return;
    }
    window.open(url, "_blank", "noopener,noreferrer");
  };
  return (
    <div className="era-page" style={{ padding: "1rem", display: "grid", gap: "1rem" }}>
      <StatusBanner
        title={needsInfo ? "Дополните заявку" : "Заявка на проверке"}
        description={needsInfo ? "Команде ЭРА не хватает данных. Откройте бот: там указано, что именно нужно дополнить." : "Пока команда знакомится с заявкой, вы можете смотреть события, проекты и возможности. Действия откроются после подтверждения."}
        actionLabel={needsInfo ? "Проверить после дополнения" : "Проверить сейчас"}
        onAction={onRefresh}
      />
      {needsInfo && <button type="button" className="era-btn-primary" onClick={openBot}>Открыть @ERA_1bot</button>}
      <div style={{ display: "grid", gap: ".55rem" }}>
        <button type="button" onClick={() => { window.location.hash = "#/participation"; }}>Посмотреть события</button>
        <button type="button" onClick={() => { window.location.hash = "#/projects"; }}>Посмотреть проекты</button>
        <button type="button" onClick={() => { window.location.hash = "#/opportunities"; }}>Посмотреть возможности</button>
      </div>
    </div>
  );
}
