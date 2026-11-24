import { Card } from "../components/Card";
import { MonoLabel } from "../components/MonoLabel";
import { EmptyState } from "../components/EmptyState";
import { useAsync } from "../hooks/useAsync";
import { fetchGamesCatalog } from "../api/client";
import type { MiniAppUserSummary } from "../types/auth";

export type DiscoverCategory = "offers" | "leisure" | "points";
const go = (path: string) => { window.location.hash = "#/" + path; };
export function DiscoverScreen({ user, category = "offers" }: { user: MiniAppUserSummary; category?: DiscoverCategory }) {
  const games = useAsync(fetchGamesCatalog, []);
  const entry = (title: string, text: string, path: string) => (
    <Card onClick={() => go(path)} key={path}>
      <strong className="era-discover-title">{title}</strong>
      <p className="era-discover-copy">{text}</p><span className="era-discover-arrow" aria-hidden="true">↗</span>
    </Card>
  );
  return <div className="era-page era-discover-page">
    <header><MonoLabel>Твоя ЭРА</MonoLabel><h1>Открытия</h1><p className="era-discover-copy">Новые возможности. Время для себя.</p></header>
    <div className="era-discover-tabs" role="group" aria-label="Разделы открытий">
      {([["offers", "Возможности"], ["leisure", "Досуг"], ["points", "За баллы"]] as const).map(([key, label]) =>
        <button key={key} aria-pressed={category === key} onClick={() => go(key === "offers" ? "discover" : "discover/" + key)}>{label}</button>)}
    </div>
    {category === "offers" && <>
      {entry("Твоя следующая возможность", "Программы, предложения и участие в новых инициативах.", "opportunities")}
      {user.features.era_pro && entry("Лидеры ЭРА", "Найди направление, в котором хочешь развиваться.", "era-pro")}
      {user.features.surveys && entry("Твой голос", "Опросы и решения сообщества.", "surveys")}
    </>}
    {category === "leisure" && <>
      {entry("Пять минут для себя", "Литература, истории и вопросы, о которых хочется подумать.", "literature")}
      {games.status === "ready" && games.data.enabled && entry("Давай сыграем", "Квизы, логика и командные игры.", "games")}
      {games.status === "error" && <EmptyState text="Не удалось проверить доступные игры." actionLabel="Повторить" onAction={games.reload} />}
    </>}
    {category === "points" && <>
      {user.features.rewards && entry("Каталог", "Выбирай награды за свой вклад.", "rewards")}
      {user.features.auctions && entry("Аукционы", "Участвуй в открытых аукционах ЭРА.", "auctions")}
      {entry("Мой вклад", "Баланс, достижения и личные результаты.", "profile")}
      {entry("Рейтинг", "Результаты участников сообщества.", "leaderboard")}
    </>}
  </div>;
}
