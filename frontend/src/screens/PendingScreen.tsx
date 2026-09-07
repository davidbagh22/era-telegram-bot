import { StatusBanner } from "../components/StatusBanner";

interface PendingScreenProps {
  onRefresh: () => void;
  status?: string;
}

export function PendingScreen({ onRefresh, status = "pending" }: PendingScreenProps) {
  const needsInfo = status === "needs_info";
  return (
    <div className="era-page" style={{ padding: "1rem", display: "grid", gap: "1rem" }}>
      <StatusBanner
        title={needsInfo ? "Дополните заявку" : "Заявка на проверке"}
        description={needsInfo ? "Команде ЭРА не хватает данных. Откройте бот: там указано, что именно нужно дополнить." : "Пока команда знакомится с заявкой, вы можете смотреть события, проекты и возможности. Действия откроются после подтверждения."}
        actionLabel={needsInfo ? "Проверить после дополнения" : "Проверить сейчас"}
        onAction={onRefresh}
      />
      <div style={{ display: "grid", gap: ".55rem" }}>
        <button type="button" onClick={() => { window.location.hash = "#/participation"; }}>Посмотреть события</button>
        <button type="button" onClick={() => { window.location.hash = "#/projects"; }}>Посмотреть проекты</button>
        <button type="button" onClick={() => { window.location.hash = "#/opportunities"; }}>Посмотреть возможности</button>
      </div>
    </div>
  );
}
