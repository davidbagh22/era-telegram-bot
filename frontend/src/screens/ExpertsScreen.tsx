import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { SkeletonList } from "../components/Skeleton";
import { useAsync } from "../hooks/useAsync";
import { fetchPublishedExperts, type PublishedExpert } from "../api/client";

interface ExpertsScreenProps {
  onBack?: () => void;
}

export function ExpertsScreen({ onBack }: ExpertsScreenProps) {
  const list = useAsync(fetchPublishedExperts, []);

  return (
    <div className="era-page era-discover-page" style={{ padding: "1.25rem", display: "grid", gap: "1rem" }}>
      <header style={{ display: "grid", gap: "0.35rem" }}>
        {onBack ? (
          <button type="button" className="era-btn-ghost" onClick={onBack} style={{ justifySelf: "start", minHeight: 44 }}>
            Назад
          </button>
        ) : null}
        <MonoLabel>Экспертная платформа</MonoLabel>
        <h1>Эксперты</h1>
        <p className="era-discover-copy">
          Люди, чьи знания помогают молодёжи создавать проекты. Публикуются только после согласия и проверки.
        </p>
      </header>

      {list.status === "loading" ? <SkeletonList count={3} /> : null}
      {list.status === "error" ? (
        <EmptyState
          title="Не удалось загрузить экспертов"
          text="Проверьте соединение и попробуйте ещё раз."
          actionLabel="Повторить"
          onAction={list.reload}
        />
      ) : null}
      {list.status === "ready" && list.data.length === 0 ? (
        <EmptyState
          title="Пока нет опубликованных экспертов"
          text="Раздел готов. Когда появятся согласованные профили, они отобразятся здесь."
        />
      ) : null}
      {list.status === "ready" && list.data.length > 0 ? (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "0.75rem" }}>
          {list.data.map((expert: PublishedExpert) => (
            <li
              key={expert.id}
              style={{
                padding: "0.9rem 1rem",
                border: "1px solid var(--era-border)",
                borderRadius: "1rem",
                background: "var(--era-surface, transparent)",
              }}
            >
              <strong style={{ display: "block", fontSize: "1rem" }}>{expert.display_name}</strong>
              {(expert.title || expert.organization) && (
                <p className="era-discover-copy" style={{ margin: "0.25rem 0 0" }}>
                  {[expert.title, expert.organization].filter(Boolean).join(" · ")}
                </p>
              )}
              {expert.bio_short ? (
                <p className="era-discover-copy" style={{ margin: "0.45rem 0 0" }}>
                  {expert.bio_short}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
