import { useCallback, useState } from "react";
import { downloadResumePdf, fetchProfile } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { ProgressBar } from "../components/ProgressBar";
import { StatusBanner } from "../components/StatusBanner";
import { useAsync } from "../hooks/useAsync";
import type { PortfolioEntry } from "../types/profile";

const GROWTH_LABELS = ["Участник", "Активный", "Лидер"];

const STAT_LABELS: Record<string, string> = {
  points: "Баллы",
  events: "Мероприятия",
  projects: "Проекты",
  completed_projects: "Завершено проектов",
  tasks: "Задачи",
  portfolio: "В портфолио",
};

function PortfolioSection({ title, entries }: { title: string; entries: PortfolioEntry[] }) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <section>
      <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
        {title}
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {entries.map((entry, index) => (
          <Card key={`${entry.title}-${index}`}>
            <strong>{entry.title}</strong>
            {entry.description && (
              <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>{entry.description}</p>
            )}
            {(entry.status || entry.date_label) && (
              <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                {[entry.status, entry.date_label].filter(Boolean).join(" · ")}
              </p>
            )}
          </Card>
        ))}
      </div>
    </section>
  );
}

export function ProfileScreen() {
  const state = useAsync(fetchProfile, []);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);

  const handleDownloadResume = useCallback(async () => {
    setDownloading(true);
    setDownloadError(false);
    try {
      const blob = await downloadResumePdf();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "ERA_portfolio.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadError(true);
    } finally {
      setDownloading(false);
    }
  }, []);

  if (state.status === "loading") {
    return <div style={{ padding: "1.5rem", color: "var(--era-text-muted)" }}>Загрузка…</div>;
  }

  if (state.status === "error") {
    return (
      <StatusBanner
        title="Не удалось загрузить профиль"
        description="Потяните вниз, чтобы обновить страницу, или откройте ЭРА заново."
      />
    );
  }

  const { data } = state;

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
          {data.full_name || data.first_name}
        </h1>
        <p style={{ color: "var(--era-text-muted)", margin: "0.25rem 0 0" }}>
          Ваш уровень: {data.growth.label}
          {data.city ? ` · ${data.city}` : ""}
        </p>
      </div>

      <ProgressBar
        currentIndex={data.growth.level_index}
        totalSteps={data.growth.level_count}
        labels={GROWTH_LABELS}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
        {Object.entries(data.stats).map(([key, value]) => (
          <MetricCard key={key} label={STAT_LABELS[key] ?? key} value={value} />
        ))}
      </div>

      {(data.departments.length > 0 || data.directions.length > 0) && (
        <Card>
          {data.departments.length > 0 && <p style={{ margin: 0 }}>Отделы: {data.departments.join(", ")}</p>}
          {data.directions.length > 0 && (
            <p style={{ margin: data.departments.length > 0 ? "0.25rem 0 0" : 0 }}>
              Направления: {data.directions.join(", ")}
            </p>
          )}
        </Card>
      )}

      <div>
        <button
          type="button"
          className="era-btn-primary"
          disabled={downloading}
          onClick={handleDownloadResume}
        >
          {downloading ? "Формируем PDF…" : "Скачать резюме PDF"}
        </button>
        {downloadError && (
          <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: "0.5rem 0 0" }}>
            Не удалось скачать резюме. Попробуйте ещё раз.
          </p>
        )}
      </div>

      <PortfolioSection title="Проекты" entries={data.projects} />
      <PortfolioSection title="Мероприятия" entries={data.events} />
      <PortfolioSection title="Задачи" entries={data.tasks} />
      <PortfolioSection title="Волонтёрство" entries={data.volunteer} />
      <PortfolioSection title="Лидерство" entries={data.leadership} />
      <PortfolioSection title="Достижения" entries={data.badges} />
      <PortfolioSection title="Сертификаты" entries={data.certificates} />
      <PortfolioSection title="Рекомендации" entries={data.recommendations} />

      {data.projects.length === 0 &&
        data.events.length === 0 &&
        data.tasks.length === 0 &&
        data.volunteer.length === 0 &&
        data.leadership.length === 0 &&
        data.badges.length === 0 &&
        data.certificates.length === 0 &&
        data.recommendations.length === 0 && (
          <EmptyState text="Портфолио пока пусто — начните с мероприятия, задачи или проекта." />
        )}
    </div>
  );
}
