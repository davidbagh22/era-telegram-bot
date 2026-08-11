import { useCallback, useState } from "react";
import { downloadDataExport, downloadResumePdf, fetchProfile, requestAccountDeletion } from "../api/client";
import { Avatar } from "../components/Avatar";
import { BottomSheet } from "../components/BottomSheet";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { ProgressBar } from "../components/ProgressBar";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useToast } from "../components/Toast";
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
  const [exporting, setExporting] = useState(false);
  const [deletionOpen, setDeletionOpen] = useState(false);
  const [requestingDeletion, setRequestingDeletion] = useState(false);
  const [deletionRequested, setDeletionRequested] = useState(false);
  const toast = useToast();

  const handleDownloadResume = useCallback(async () => {
    setDownloading(true);
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
      toast.show("Резюме сохранено", "success");
    } catch {
      toast.show("Не удалось скачать резюме. Попробуйте ещё раз.", "error");
    } finally {
      setDownloading(false);
    }
  }, [toast]);

  const handleExportData = useCallback(async () => {
    setExporting(true);
    try {
      const blob = await downloadDataExport();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "ERA_data_export.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.show("Данные выгружены", "success");
    } catch {
      toast.show("Не удалось выгрузить данные. Попробуйте ещё раз.", "error");
    } finally {
      setExporting(false);
    }
  }, [toast]);

  const handleRequestDeletion = useCallback(async () => {
    setRequestingDeletion(true);
    try {
      await requestAccountDeletion();
      setDeletionRequested(true);
      setDeletionOpen(false);
      toast.show("Заявка на удаление аккаунта отправлена администратору", "success");
    } catch {
      toast.show("Не удалось отправить заявку. Попробуйте ещё раз.", "error");
    } finally {
      setRequestingDeletion(false);
    }
  }, [toast]);

  if (state.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Skeleton width={48} height={48} radius="50%" />
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <Skeleton height="1.125rem" width="55%" />
            <Skeleton height="0.75rem" width="35%" />
          </div>
        </div>
        <Skeleton height="2.5rem" radius="var(--era-radius-control)" />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
          <Skeleton height="4rem" radius="var(--era-radius-card)" />
          <Skeleton height="4rem" radius="var(--era-radius-card)" />
          <Skeleton height="4rem" radius="var(--era-radius-card)" />
        </div>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
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
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <Avatar firstName={data.first_name} lastName={data.last_name} />
        <div>
          <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)", margin: 0 }}>
            {data.full_name || data.first_name}
          </h1>
          <p style={{ color: "var(--era-text-muted)", margin: "0.25rem 0 0" }}>
            Ваш уровень: {data.growth.label}
            {data.city ? ` · ${data.city}` : ""}
          </p>
        </div>
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

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <button
          type="button"
          className="era-btn-primary"
          disabled={downloading}
          onClick={handleDownloadResume}
        >
          {downloading ? "Формируем PDF…" : "Скачать резюме PDF"}
        </button>
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

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Данные и конфиденциальность
        </h2>
        <Card>
          <p style={{ margin: "0 0 0.75rem", color: "var(--era-text-muted)" }}>
            Скачайте копию всех данных, которые ЭРА хранит о вас, или запросите удаление аккаунта.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <button type="button" disabled={exporting} onClick={handleExportData}>
              {exporting ? "Готовим файл…" : "Скачать мои данные (JSON)"}
            </button>
            <button
              type="button"
              disabled={deletionRequested}
              onClick={() => setDeletionOpen(true)}
              style={{ color: "var(--era-error)" }}
            >
              {deletionRequested ? "Заявка на удаление отправлена" : "Запросить удаление аккаунта"}
            </button>
          </div>
        </Card>
      </section>

      <BottomSheet
        open={deletionOpen}
        onClose={() => setDeletionOpen(false)}
        title="Запросить удаление аккаунта?"
      >
        <p style={{ color: "var(--era-text-muted)", margin: "0 0 1rem" }}>
          Заявку рассмотрит администратор. После подтверждения ваши личные данные будут обезличены,
          а аккаунт — архивирован. Это действие нельзя отменить самостоятельно.
        </p>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button type="button" onClick={() => setDeletionOpen(false)} style={{ flex: 1 }}>
            Отмена
          </button>
          <button
            type="button"
            className="era-btn-primary"
            disabled={requestingDeletion}
            onClick={handleRequestDeletion}
            style={{ flex: 1 }}
          >
            {requestingDeletion ? "Отправляем…" : "Отправить заявку"}
          </button>
        </div>
      </BottomSheet>
    </div>
  );
}
