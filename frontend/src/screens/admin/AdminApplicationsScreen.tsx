import { useCallback, useState } from "react";
import {
  approveApplication,
  describeActionError,
  fetchAdminApplications,
  rejectApplication,
  requestApplicationInfo,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { InitialsAvatar } from "../../components/InitialsAvatar";
import { useAsync } from "../../hooks/useAsync";
import type { PendingApplication } from "../../types/admin";

const STATUS_LABELS: Record<string, string> = {
  pending: "На рассмотрении",
  needs_info: "Нужна информация",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU").format(date);
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function ValueRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  const shown = value === null || value === undefined || value === "" ? "—" : String(value);
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(7.5rem, 0.9fr) minmax(0, 1.6fr)",
        gap: "0.75rem",
        padding: "0.45rem 0",
        borderBottom: "1px solid var(--era-border)",
        alignItems: "start",
      }}
    >
      <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>{label}</span>
      <span style={{ minWidth: 0, overflowWrap: "anywhere", fontSize: "0.875rem" }}>{shown}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
      <h3
        style={{
          margin: "0 0 0.35rem",
          fontSize: "0.75rem",
          color: "var(--era-text-muted)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        {title}
      </h3>
      {children}
    </section>
  );
}

function ApplicationCard({
  application,
  busy,
  comment,
  onComment,
  onApprove,
  onRequestInfo,
  onReject,
}: {
  application: PendingApplication;
  busy: boolean;
  comment: string;
  onComment: (value: string) => void;
  onApprove: () => void;
  onRequestInfo: () => void;
  onReject: () => void;
}) {
  const fullName = `${application.first_name} ${application.last_name ?? ""}`.trim();
  const telegram = application.username ? `@${application.username}` : `ID ${application.telegram_id}`;
  const departments = application.departments.length ? application.departments.join(", ") : "Не выбраны";
  const directions = application.directions.length ? application.directions.join(", ") : "Не выбраны";
  const skills = application.skills.length ? application.skills.join(", ") : "—";

  return (
    <Card style={{ borderLeft: "3px solid var(--era-gold)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.85rem" }}>
        <InitialsAvatar firstName={application.first_name} lastName={application.last_name} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <strong style={{ display: "block", fontSize: "1rem", overflowWrap: "anywhere" }}>{fullName}</strong>
          <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
            Заявка #{application.id} · {STATUS_LABELS[application.application_status] ?? application.application_status}
          </span>
        </div>
      </div>

      {application.photo_data_url ? (
        <img
          src={application.photo_data_url}
          alt={`Фото участника ${fullName}`}
          style={{
            display: "block",
            width: "100%",
            maxHeight: "28rem",
            objectFit: "cover",
            objectPosition: "center",
            borderRadius: "0.875rem",
            border: "1px solid var(--era-border)",
            marginBottom: "1rem",
            background: "var(--era-bg)",
          }}
        />
      ) : application.photo_attached ? (
        <div
          style={{
            padding: "1rem",
            border: "1px solid var(--era-border)",
            borderRadius: "0.875rem",
            color: "var(--era-text-muted)",
            marginBottom: "1rem",
          }}
        >
          Фото прикреплено, но временно не удалось загрузить. Обновите экран позже.
        </div>
      ) : (
        <div
          style={{
            padding: "1rem",
            border: "1px solid var(--era-border)",
            borderRadius: "0.875rem",
            color: "var(--era-error)",
            marginBottom: "1rem",
          }}
        >
          Фото в заявке отсутствует.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <Section title="Личные данные">
          <ValueRow label="Имя и фамилия" value={fullName} />
          <ValueRow label="Дата рождения" value={formatDate(application.birth_date)} />
          <ValueRow label="Возраст" value={application.age} />
          <ValueRow label="Город" value={application.city} />
        </Section>

        <Section title="Контакты">
          <ValueRow label="Telegram" value={telegram} />
          <ValueRow label="Telegram ID" value={application.telegram_id} />
          <ValueRow label="Телефон" value={application.phone} />
          <ValueRow label="Email" value={application.email} />
          {application.social_links.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", paddingTop: "0.5rem" }}>
              <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>Соцсети</span>
              {application.social_links.map((link) => (
                <a
                  key={`${link.platform}:${link.url}`}
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ overflowWrap: "anywhere" }}
                >
                  {link.platform}: {link.url}
                </a>
              ))}
            </div>
          ) : (
            <ValueRow label="Соцсети" value="—" />
          )}
        </Section>

        <Section title="Учёба и деятельность">
          <ValueRow label="Учёба / работа" value={application.education_work} />
          <ValueRow label="Занятие" value={application.occupation} />
          <ValueRow label="Навыки" value={skills} />
          {application.experience && <ValueRow label="Опыт" value={application.experience} />}
        </Section>

        <Section title="Интерес к ЭРА">
          <ValueRow label="Департамент" value={departments} />
          <ValueRow label="Направления" value={directions} />
          <ValueRow label="Доступное время" value={application.available_time} />
          <ValueRow label="Желаемый путь" value={application.desired_path} />
        </Section>

        <Section title="Мотивация">
          <p
            style={{
              margin: 0,
              padding: "0.85rem",
              borderRadius: "0.75rem",
              background: "var(--era-bg)",
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere",
              lineHeight: 1.55,
            }}
          >
            {application.motivation || "—"}
          </p>
        </Section>

        <Section title="Согласие и подача">
          <ValueRow label="Обработка данных" value={application.personal_data_consent ? "Согласие получено" : "Нет согласия"} />
          <ValueRow label="Версия условий" value={application.consent_policy_version} />
          <ValueRow label="Дата подачи" value={formatDateTime(application.created_at)} />
        </Section>
      </div>

      <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--era-border)" }}>
        <textarea
          placeholder="Комментарий (для отклонения или запроса информации)"
          value={comment}
          onChange={(event) => onComment(event.target.value)}
          rows={3}
          style={{
            width: "100%",
            boxSizing: "border-box",
            fontFamily: "var(--era-font-body)",
            padding: "0.75rem",
            borderRadius: "0.75rem",
            border: "1px solid var(--era-border)",
            background: "var(--era-bg)",
            color: "var(--era-text)",
            marginBottom: "0.65rem",
            resize: "vertical",
          }}
        />
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button type="button" className="era-btn-primary" disabled={busy} onClick={onApprove}>
            Одобрить
          </button>
          <button type="button" disabled={busy || !comment.trim()} onClick={onRequestInfo}>
            Запросить информацию
          </button>
          <button type="button" disabled={busy || !comment.trim()} onClick={onReject}>
            Отклонить
          </button>
        </div>
      </div>
    </Card>
  );
}

export function AdminApplicationsScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminApplications(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleApprove = useCallback(
    async (userId: number) => {
      setBusyId(userId);
      setActionError(null);
      try {
        await approveApplication(userId);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  const handleReject = useCallback(
    async (userId: number) => {
      const comment = (comments[userId] ?? "").trim();
      if (!comment) return;
      setBusyId(userId);
      setActionError(null);
      try {
        await rejectApplication(userId, comment);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [comments, refresh],
  );

  const handleRequestInfo = useCallback(
    async (userId: number) => {
      const comment = (comments[userId] ?? "").trim();
      if (!comment) return;
      setBusyId(userId);
      setActionError(null);
      try {
        await requestApplicationInfo(userId, comment);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [comments, refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка полной анкеты и фотографии…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить заявки." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Новых заявок нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem", minWidth: 0 }}>
      <div>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          Показаны все данные, которые участник отправил при регистрации, включая фотографию и соцсети.
        </p>
      </div>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((application) => (
        <ApplicationCard
          key={application.id}
          application={application}
          busy={busyId === application.id}
          comment={comments[application.id] ?? ""}
          onComment={(value) =>
            setComments((previous) => ({ ...previous, [application.id]: value }))
          }
          onApprove={() => handleApprove(application.id)}
          onRequestInfo={() => handleRequestInfo(application.id)}
          onReject={() => handleReject(application.id)}
        />
      ))}
    </div>
  );
}
