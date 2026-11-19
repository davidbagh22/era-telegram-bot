import { fetchTeams } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { TypographyFeedCard } from "../components/TypographyFeedCard";
import { SkeletonList } from "../components/Skeleton";
import { useAsync } from "../hooks/useAsync";
import { formatProjectFeedDate } from "../utils/feedDate";
import { displayProjectTitle } from "./projects/displayTitle";

interface TeamsScreenProps {
  onOpenProject?: (projectId: number) => void;
  onBack?: () => void;
}

/** Teams = existing projects/memberships — no parallel team entity. */
export function TeamsScreen({ onOpenProject, onBack }: TeamsScreenProps) {
  const mine = useAsync(() => fetchTeams("mine"), []);
  const open = useAsync(() => fetchTeams("open"), []);

  const loading = mine.status === "loading" || open.status === "loading";
  const openTeams = open.status === "ready"
    ? open.data.filter(project => mine.status !== "ready" || !mine.data.some(item => item.id === project.id))
    : [];

  return (
    <div className="era-page" style={{ padding: "1.15rem 1.15rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.1rem" }}>
      {onBack && (
        <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>
          ← Орбита
        </button>
      )}
      <header>
        <MonoLabel>Орбита</MonoLabel>
        <h1 style={{ margin: "0.35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem" }}>Команды</h1>
        <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.9rem" }}>
          Найди свою команду и создавай вместе.
        </p>
      </header>

      {loading && <SkeletonList count={3} />}
      {mine.status === "error" && <EmptyState text="Не удалось загрузить мои команды." actionLabel="Повторить" onAction={mine.reload} />}
      {open.status === "error" && <EmptyState text="Не удалось загрузить открытые команды." actionLabel="Повторить" onAction={open.reload} />}

      {mine.status === "ready" && (
        <section style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
          <MonoLabel>Мои</MonoLabel>
          {mine.data.length === 0 ? (
            <EmptyState text="Пока нет своих команд. Можно вступить в открытый набор или предложить идею." />
          ) : (
            mine.data.map((project) => (
              <TypographyFeedCard
                key={`mine-${project.id}`}
                title={displayProjectTitle(project.title)}
                dateLine={formatProjectFeedDate({
                  proposedDate: project.proposed_date,
                  proposedTime: project.proposed_time,
                  dateIsTentative: project.date_is_tentative,
                })}
                onClick={() => onOpenProject?.(project.id)}
              />
            ))
          )}
        </section>
      )}

      {open.status === "ready" && (
        <section style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
          <MonoLabel>Открытые команды</MonoLabel>
          {openTeams.length === 0 ? (
            <EmptyState text="Сейчас нет проектов с открытым набором." />
          ) : (
            openTeams.map((project) => (
              <TypographyFeedCard
                key={`open-${project.id}`}
                title={displayProjectTitle(project.title)}
                dateLine={formatProjectFeedDate({
                  proposedDate: project.proposed_date,
                  proposedTime: project.proposed_time,
                  dateIsTentative: project.date_is_tentative,
                })}
                onClick={() => onOpenProject?.(project.id)}
              />
            ))
          )}
        </section>
      )}
    </div>
  );
}
