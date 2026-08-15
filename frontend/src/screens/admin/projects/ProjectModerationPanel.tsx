import { useCallback, useState } from "react";
import { fetchAdminProjectDetail } from "../../../api/adminProjectDetail";
import { decideProject, describeActionError, fetchAdminProjects } from "../../../api/client";
import { BottomSheet } from "../../../components/BottomSheet";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { projectStatusLabel } from "../../projects/statusLabels";
import type { ProjectDecisionAction, ProjectForModeration } from "../../../types/admin";

const DECISIONS: { action: ProjectDecisionAction; label: string; primary?: boolean }[] = [
  { action: "initial_accept", label: "Принять в работу", primary: true },
  { action: "venue_approve", label: "Одобрить", primary: true },
  { action: "revise", label: "На доработку" },
  { action: "postpone", label: "Перенести" },
  { action: "reject", label: "Отклонить" },
];

const FIELD_LABELS: Record<string, string> = {
  title: "Название",
  idea: "Суть идеи",
  relevance: "Почему это важно",
  goal: "Цель",
  tasks: "Задачи проекта",
  target_audience: "Аудитория",
  format: "Формат",
  program: "Программа",
  resources: "Ресурсы",
  team: "Команда",
  risks: "Риски",
  needs_from_era: "Что нужно от ЭРА",
  success_metrics: "Ожидаемый результат",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function visibleFields(formData: Record<string, unknown>) {
  return Object.entries(formData).filter(([key, value]) => {
    if (key.startsWith("team_search_") || key.startsWith("_")) return false;
    return typeof value === "string" && value.trim().length > 0;
  });
}

function OpenProjectReview({
  project,
  onBack,
  onDone,
}: {
  project: ProjectForModeration;
  onBack: () => void;
  onDone: () => void;
}) {
  const detail = useAsync(() => fetchAdminProjectDetail(project.id), [project.id]);
  const [showDecisionSheet, setShowDecisionSheet] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleDecide = async (action: ProjectDecisionAction) => {
    const trimmed = comment.trim();
    if (!trimmed) return;
    setBusy(true);
    setActionError(null);
    try {
      await decideProject(project.id, action, trimmed);
      onDone();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setBusy(false);
    }
  };

  if (detail.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Открываем полный проект…</p>;
  }
  if (detail.status === "error") {
    return <EmptyState text="Не удалось загрузить полный проект. Решение не отправлено." />;
  }

  const fields = visibleFields(detail.data.form_data);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack}>← К проектам на рассмотрении</button>
      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}

      <Card gradient>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "flex-start" }}>
          <div>
            <p style={{ margin: 0, opacity: 0.72, fontSize: "0.72rem", fontWeight: 800, textTransform: "uppercase" }}>Проект на проверке</p>
            <strong style={{ display: "block", marginTop: "0.2rem", fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-xl)" }}>{detail.data.title}</strong>
            <p style={{ margin: "0.35rem 0 0", opacity: 0.82, fontSize: "0.8rem" }}>Автор: {detail.data.author_name}</p>
          </div>
          <StatusBadge label={projectStatusLabel(detail.data.status)} tone="violet" />
        </div>
        <p style={{ margin: "0.45rem 0 0", opacity: 0.72, fontSize: "0.75rem" }}>Подан {formatDate(detail.data.submitted_at)}</p>
      </Card>

      <Card>
        <strong>Суть проекта</strong>
        <p style={{ margin: "0.4rem 0 0", lineHeight: 1.5 }}>{detail.data.short_description || "Не заполнено"}</p>
      </Card>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "baseline" }}>
          <strong>Полный паспорт проекта</strong>
          <span style={{ color: "var(--era-text-muted)", fontSize: "0.72rem" }}>{fields.length} блоков</span>
        </div>
        {fields.length === 0 ? (
          <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>Автор ещё не заполнил структурные блоки.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem", marginTop: "0.75rem" }}>
            {fields.map(([key, value]) => (
              <div key={key}>
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.75rem", fontWeight: 800 }}>{FIELD_LABELS[key] ?? key.replace(/_/g, " ")}</p>
                <p style={{ margin: "0.25rem 0 0", whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{String(value)}</p>
              </div>
            ))}
          </div>
        )}
      </Card>

      {detail.data.admin_comment && (
        <Card>
          <strong>Предыдущий комментарий</strong>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{detail.data.admin_comment}</p>
        </Card>
      )}

      <button type="button" className="era-btn-primary" onClick={() => setShowDecisionSheet(true)}>
        Принять решение
      </button>

      <BottomSheet open={showDecisionSheet} onClose={() => setShowDecisionSheet(false)} title="Решение по проекту">
        <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.4 }}>
            Сначала проект, потом решение. Комментарий увидит автор.
          </p>
          <textarea
            placeholder="Что автору важно знать по этому решению?"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={3}
          />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
            {DECISIONS.map(({ action, label, primary }) => (
              <button
                key={action}
                type="button"
                className={primary ? "era-btn-primary" : undefined}
                disabled={busy || !comment.trim()}
                onClick={() => void handleDecide(action)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </BottomSheet>
    </div>
  );
}

export function ProjectModerationPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminProjects(), [refreshKey]);
  const [openId, setOpenId] = useState<number | null>(null);
  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  if (state.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  if (state.status === "error") return <EmptyState text="Не удалось загрузить проекты." />;
  if (state.data.length === 0) return <EmptyState text="Проектов на рассмотрении нет." />;

  const open = state.data.find((project) => project.id === openId) ?? null;
  if (open) {
    return (
      <OpenProjectReview
        project={open}
        onBack={() => setOpenId(null)}
        onDone={() => {
          setOpenId(null);
          refresh();
        }}
      />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {state.data.map((project: ProjectForModeration) => (
        <Card key={project.id}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
            <strong>{project.title}</strong>
            <StatusBadge label={projectStatusLabel(project.status)} tone="violet" />
          </div>
          {project.short_description && <p style={{ margin: "0.375rem 0 0", color: "var(--era-text-muted)" }}>{project.short_description}</p>}
          <p style={{ margin: "0.375rem 0 0.5rem", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>Подан {formatDate(project.submitted_at)}</p>
          <button type="button" onClick={() => setOpenId(project.id)}>Открыть полный проект →</button>
        </Card>
      ))}
    </div>
  );
}
