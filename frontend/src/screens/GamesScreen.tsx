import { fetchGamesCatalog } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { SkeletonList } from "../components/Skeleton";
import { useAsync } from "../hooks/useAsync";
import { getTelegramWebApp } from "../telegram/webApp";

export function GamesScreen() {
  const games = useAsync(fetchGamesCatalog, []);
  return <div className="era-page era-discover-page">
    <button className="era-btn-ghost" style={{ alignSelf: "flex-start" }} onClick={() => { window.location.hash = "#/discover/leisure"; }}>← Открытия</button>
    <header><MonoLabel>Досуг</MonoLabel><h1>Игры</h1></header>
    {games.status === "loading" && <SkeletonList count={3} />}
    {games.status === "error" && <EmptyState text="Не удалось загрузить игры." actionLabel="Повторить" onAction={games.reload} />}
    {games.status === "ready" && (!games.data.enabled ? <EmptyState text="Игры пока недоступны для вашего аккаунта." /> : <>
      <p className="era-discover-copy">Выбери настроение. Игру продолжит бот в Telegram.</p>
      <button className="era-btn-primary" onClick={() => {
        const url = games.data.launch_url;
        if (!url) return;
        const app = getTelegramWebApp();
        if (app?.openTelegramLink) app.openTelegramLink(url);
        else window.open(url, "_blank", "noopener,noreferrer");
      }}>Открыть меню игр в Telegram ↗</button>
      {games.data.items.map(item => <Card key={item.id}><MonoLabel>{item.group ? "Вместе" : "Соло"} · {item.players} игроков · {item.minutes} мин</MonoLabel><h2>{item.title}</h2><p className="era-discover-copy">{item.rules}</p></Card>)}
    </>)}
  </div>;
}
