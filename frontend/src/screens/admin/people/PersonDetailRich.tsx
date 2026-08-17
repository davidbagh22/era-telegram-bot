import { useCallback, useState } from "react";
import {
  awardUserBadge,
  awardUserPoints,
  changeUserRole,
  describeActionError,
  fetchAdminUserDetail,
  setUserArchived,
  setUserBlocked,
  toggleUserPermission,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import type { BadgeItem, UserDetail } from "../../../types/admin";
import {
  PERMISSION_DESCRIPTIONS,
  PERMISSION_LABELS,
  ROLE_LABELS,
  ROLE_OPTIONS,
} from "./roleLabels";

// Points/Ranks ToR section 44: a large manual award needs an explicit
// second confirmation, not just a single tap/typo -- matches the backend
// gate at app/api/v1/admin.py::LARGE_MANUAL_AWARD_THRESHOLD.
const LARGE_MANUAL_AWARD_THRESHOLD = 300;

function isLargeManualAward(amount: number): boolean {
  return Math.abs(amount) > LARGE_MANUAL_AWARD_THRESHOLD;
}

function confirmLargeManualAward(amount: number): boolean {
  if (!isLargeManualAward(amount)) return true;
  return window.confirm(
    `Начислить ${amount > 0 ? "+" : ""}${amount} баллов? Это крупная ручная корректировка — подтвердите, что это осознанное решение.`,
  );
}

const inputStyle = {
  fontFamily: "var(--era-font-body)",
  padding: "0.7rem",
  borderRadius: "0.7rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
  width: "100%",
  boxSizing: "border-box",
} as const;

const BADGE_DESCRIPTIONS: Record<string, string> = {
  "Первый шаг": "Первое подтверждённое действие в ЭРА.",
  "Голос ЭРА": "Содержательная обратная связь и участие в жизни сообщества.",
  "Надёжный участник": "Стабильность, ответственность и доведение действий до результата.",
  "Командный игрок": "Подтверждённый вклад в общую работу и проектную команду.",
  "Организатор": "Ответственность за подготовку и проведение мероприятий.",
  "Проектный автор": "Инициатива и запуск собственного проекта.",
  "Медиа-двигатель": "Подтверждённая активность в медиа-направлении.",
  "Амбассадор ЭРА": "Представление ЭРА вовне и расширение сообщества.",
  "Наставник": "Помощь другим участникам в росте и развитии.",
  "Прорыв месяца": "Заметный рост активности и результатов за короткий период.",
};

type ViewKey = "overview" | "activity" | "surveys" | "management";

type ActivityRecord = {
  id: number;
  title: string;
  subtitle: string | null;
  status: string | null;
  date: string | null;
  points: number | null;
};

type OwnedBadge = BadgeItem & {
  description?: string | null;
  reason?: string | null;
  awarded_at?: string | null;
};

type BadgeSuggestion = {
  badge_id: number;
  badge_name: string;
  reason: string;
  evidence: string[];
};

type RichUserDetail = UserDetail & {
  birth_date: string | null;
  age: number | null;
  education_work: string | null;
  skills: string[];
  experience: string | null;
  available_time: string | null;
  desired_path: string | null;
  departments: string[];
  directions: string[];
  created_at: string;
  photo_attached: boolean;
  photo_data_url: string | null;
  metrics: {
    events_registered: number;
    events_attended: number;
    no_shows: number;
    tasks_submitted: number;
    tasks_approved: number;
    projects_authored: number;
    project_memberships: number;
    confirmed_project_contributions: number;
    surveys_completed: number;
    activity_submissions_approved: number;
    events_responsible: number;
    points_transactions: number;
  };
  leadership: {
    summary: string;
    strengths: string[];
    growth_areas: string[];
  };
  points_suggestion: {
    amount: number;
    reason: string;
    evidence: string[];
  } | null;
  badge_suggestions: BadgeSuggestion[];
  activity: {
    events: ActivityRecord[];
    tasks: ActivityRecord[];
    projects: ActivityRecord[];
    point_history: ActivityRecord[];
    portfolio: ActivityRecord[];
  };
  surveys: {
    id: number;
    title: string;
    submitted_at: string | null;
    answers: { question: string; answer: string }[];
  }[];
};

interface PersonDetailProps {
  userId: number;
  onBack: () => void;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parsed);
}

function prettyStatus(value: string | null | undefined): string {
  if (!value) return "—";
  const labels: Record<string, string> = {
    approved: "Одобрено",
    pending: "На рассмотрении",
    completed: "Завершено",
    in_progress: "В работе",
    attended: "Посетил",
    registered: "Зарегистрирован",
    will_come: "Подтвердил участие",
    cancelled: "Отменено",
    no_show: "Не пришёл",
    rejected: "Отклонено",
    needs_info: "Нужна информация",
    confirmed: "Подтверждено",
    new_member: "Новый участник",
    involved_member: "Вовлечённый участник",
    active_member: "Активный участник",
    team_member: "Член команды",
    project_curator: "Куратор проекта",
    community_leader: "Лидер сообщества",
  };
  return labels[value] ?? value.split("_").join(" ");
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(7rem, .9fr) minmax(0, 1.5fr)",
        gap: "0.75rem",
        padding: "0.5rem 0",
        borderBottom: "1px solid var(--era-border)",
      }}
    >
      <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>{label}</span>
      <span style={{ minWidth: 0, overflowWrap: "anywhere", fontSize: "0.875rem" }}>{value || "—"}</span>
    </div>
  );
}

function Metric({ value, label }: { value: string | number; label: string }) {
  return (
    <div
      style={{
        padding: "0.8rem",
        border: "1px solid var(--era-border)",
        borderRadius: "0.85rem",
        background: "var(--era-bg)",
      }}
    >
      <strong style={{ display: "block", fontSize: "1.3rem" }}>{value}</strong>
      <span style={{ color: "var(--era-text-muted)", fontSize: "0.75rem", lineHeight: 1.3 }}>{label}</span>
    </div>
  );
}

function ActivityList({ items, empty }: { items: ActivityRecord[]; empty: string }) {
  if (items.length === 0) {
    return <p style={{ color: "var(--era-text-muted)", margin: 0 }}>{empty}</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
      {items.map((item) => (
        <div
          key={`${item.id}-${item.title}-${item.date ?? ""}`}
          style={{ padding: "0.75rem", border: "1px solid var(--era-border)", borderRadius: "0.8rem" }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.65rem", alignItems: "flex-start" }}>
            <strong style={{ fontSize: "0.875rem" }}>{item.title}</strong>
            {item.points !== null && item.points !== undefined && (
              <span style={{ fontWeight: 800, whiteSpace: "nowrap" }}>
                {item.points > 0 ? "+" : ""}{item.points}
              </span>
            )}
          </div>
          {(item.subtitle || item.status || item.date) && (
            <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "0.75rem", lineHeight: 1.45 }}>
              {[item.subtitle, item.status ? prettyStatus(item.status) : null, item.date ? formatDate(item.date) : null]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

export function PersonDetail({ userId, onBack }: PersonDetailProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminUserDetail(userId), [userId, refreshKey]);
  const [view, setView] = useState<ViewKey>("overview");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pointsAmount, setPointsAmount] = useState("");
  const [pointsReason, setPointsReason] = useState("");
  const [selectedBadgeId, setSelectedBadgeId] = useState("");
  const [badgeReason, setBadgeReason] = useState("");

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);
  const runAction = useCallback(
    async (action: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await action();
        refresh();
      } catch (err) {
        setError(describeActionError(err));
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка полной карточки участника…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить участника." />;
  }

  const person = state.data as RichUserDetail;
  const availableBadges = person.available_badges as OwnedBadge[];
  const ownedBadges = person.badges as OwnedBadge[];
  const selectedBadge = availableBadges.find((badge) => String(badge.id) === selectedBadgeId);
  const metrics: readonly (readonly [number, string])[] = [
    [person.metrics.events_attended, "Посещено событий"],
    [person.metrics.tasks_approved, "Принято заданий"],
    [person.metrics.projects_authored, "Своих проектов"],
    [person.metrics.project_memberships, "Проектных команд"],
    [person.metrics.surveys_completed, "Опросов заполнено"],
    [person.points_balance, "Баллов сейчас"],
  ];
  const tabs: { key: ViewKey; label: string }[] = [
    { key: "overview", label: "Обзор" },
    { key: "activity", label: "Активность" },
    { key: "surveys", label: "Опросы" },
    { key: "management", label: "Управление" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", minWidth: 0 }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← К участникам</button>
      {error && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{error}</p>}

      <Card>
        <div style={{ display: "flex", gap: "0.9rem", alignItems: "center", flexWrap: "wrap" }}>
          {person.photo_data_url ? (
            <img
              src={person.photo_data_url}
              alt="Фото участника"
              style={{
                width: "5.75rem",
                height: "5.75rem",
                objectFit: "cover",
                borderRadius: "1.15rem",
                border: "1px solid var(--era-border)",
              }}
            />
          ) : (
            <div
              style={{
                width: "5.75rem",
                height: "5.75rem",
                borderRadius: "1.15rem",
                display: "grid",
                placeItems: "center",
                background: "var(--era-bg)",
                border: "1px solid var(--era-border)",
                color: "var(--era-text-muted)",
                fontSize: "0.75rem",
                textAlign: "center",
                padding: "0.35rem",
                boxSizing: "border-box",
              }}
            >
              {person.photo_attached ? "Фото временно не загрузилось" : "Фото не загружено"}
            </div>
          )}
          <div style={{ flex: "1 1 12rem", minWidth: 0 }}>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.75rem", fontWeight: 800, textTransform: "uppercase" }}>
              Карточка участника
            </p>
            <h2 style={{ margin: "0.2rem 0 0", fontSize: "1.35rem", overflowWrap: "anywhere" }}>
              {person.first_name} {person.last_name ?? ""}
            </h2>
            <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              {person.username ? `@${person.username}` : `Telegram ID ${person.telegram_id}`} · #{person.id}
            </p>
            <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap", marginTop: "0.55rem" }}>
              <StatusBadge label={ROLE_LABELS[person.role] ?? person.role} tone="neutral" />
              <StatusBadge label={prettyStatus(person.participation_status)} tone="neutral" />
              {person.is_blocked && <StatusBadge label="Заблокирован" tone="red" />}
              {person.is_archived && <StatusBadge label="В архиве" tone="neutral" />}
            </div>
          </div>
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: "0.4rem" }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setView(tab.key)}
            className={view === tab.key ? "era-btn-primary" : undefined}
            style={{ padding: "0.65rem 0.35rem", fontSize: "0.75rem" }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {view === "overview" && (
        <>
          <Card>
            <strong>Показатели участника</strong>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.55rem", marginTop: "0.75rem" }}>
              {metrics.map(([value, label]) => <Metric key={label} value={value} label={label} />)}
            </div>
          </Card>

          <Card>
            <strong>Сигналы для руководителя</strong>
            <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem", lineHeight: 1.5 }}>
              {person.leadership.summary} Оценка строится только на действиях, которые есть в системе — это не психологическая характеристика человека.
            </p>
            {person.leadership.strengths.length > 0 && (
              <div style={{ marginTop: "0.8rem" }}>
                <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--era-text-muted)", textTransform: "uppercase" }}>
                  Подтверждённые сильные сигналы
                </span>
                {person.leadership.strengths.map((item) => (
                  <p key={item} style={{ margin: "0.4rem 0 0", fontSize: "0.875rem" }}>✓ {item}</p>
                ))}
              </div>
            )}
            {person.leadership.growth_areas.length > 0 && (
              <div style={{ marginTop: "0.8rem" }}>
                <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--era-text-muted)", textTransform: "uppercase" }}>
                  Что стоит развить
                </span>
                {person.leadership.growth_areas.map((item) => (
                  <p key={item} style={{ margin: "0.4rem 0 0", fontSize: "0.875rem" }}>→ {item}</p>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <strong>Анкета при регистрации</strong>
            <div style={{ marginTop: "0.55rem" }}>
              <InfoRow label="Дата рождения" value={`${formatDate(person.birth_date)}${person.age ? ` · ${person.age} лет` : ""}`} />
              <InfoRow label="Город" value={person.city ?? "—"} />
              <InfoRow label="Телефон" value={person.phone ?? "—"} />
              <InfoRow label="Email" value={person.email ?? "—"} />
              <InfoRow label="Учёба / работа" value={person.education_work ?? "—"} />
              <InfoRow label="Занятие" value={person.occupation ?? "—"} />
              <InfoRow label="Навыки" value={person.skills.length ? person.skills.join(", ") : "—"} />
              <InfoRow label="Опыт" value={person.experience ?? "—"} />
              <InfoRow label="Департаменты" value={person.departments.length ? person.departments.join(", ") : "—"} />
              <InfoRow label="Направления" value={person.directions.length ? person.directions.join(", ") : "—"} />
              <InfoRow label="Доступное время" value={person.available_time ?? "—"} />
              <InfoRow label="Желаемый путь" value={person.desired_path ?? "—"} />
              <InfoRow label="Мотивация" value={person.motivation ?? "—"} />
              <InfoRow label="Статус заявки" value={prettyStatus(person.application_status)} />
              <InfoRow label="Дата регистрации" value={formatDate(person.created_at)} />
            </div>
            {person.social_links.length > 0 && (
              <div style={{ marginTop: "0.8rem" }}>
                <strong style={{ fontSize: "0.8125rem" }}>Соцсети</strong>
                {person.social_links.map((link) => (
                  <a
                    key={`${link.platform}:${link.url}`}
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ display: "block", marginTop: "0.35rem", fontSize: "0.8125rem", overflowWrap: "anywhere" }}
                  >
                    {link.platform}: {link.url}
                  </a>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      {view === "activity" && (
        <>
          <Card><strong>Мероприятия</strong><div style={{ marginTop: "0.7rem" }}><ActivityList items={person.activity.events} empty="Участие в мероприятиях пока не зафиксировано." /></div></Card>
          <Card><strong>Проекты</strong><div style={{ marginTop: "0.7rem" }}><ActivityList items={person.activity.projects} empty="Проектной активности пока нет." /></div></Card>
          <Card><strong>Задания</strong><div style={{ marginTop: "0.7rem" }}><ActivityList items={person.activity.tasks} empty="Результаты заданий пока не отправлялись." /></div></Card>
          <Card><strong>История баллов</strong><div style={{ marginTop: "0.7rem" }}><ActivityList items={person.activity.point_history} empty="Операций с баллами пока нет." /></div></Card>
          <Card><strong>Портфолио и достижения</strong><div style={{ marginTop: "0.7rem" }}><ActivityList items={person.activity.portfolio} empty="Портфолио пока пустое." /></div></Card>
        </>
      )}

      {view === "surveys" && (
        <Card>
          <strong>Ответы участника на опросы</strong>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
            Здесь можно увидеть интересы, ожидания и обратную связь человека в динамике.
          </p>
          {person.surveys.length === 0 ? (
            <p style={{ color: "var(--era-text-muted)", marginBottom: 0 }}>Участник пока не заполнял опросы.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.8rem" }}>
              {person.surveys.map((survey) => (
                <div key={survey.id} style={{ padding: "0.85rem", border: "1px solid var(--era-border)", borderRadius: "0.85rem" }}>
                  <strong>{survey.title}</strong>
                  <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.75rem" }}>{formatDate(survey.submitted_at)}</p>
                  {survey.answers.map((answer, index) => (
                    <div key={`${survey.id}-${index}`} style={{ marginTop: "0.65rem" }}>
                      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.75rem" }}>{answer.question}</p>
                      <p style={{ margin: "0.2rem 0 0", fontSize: "0.875rem", whiteSpace: "pre-wrap" }}>{answer.answer}</p>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {view === "management" && (
        <>
          {person.can_manage && (
            <Card>
              <strong>Роль и статус доступа</strong>
              <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                Роль определяет место человека в системе. Точечные права ниже можно выдавать отдельно.
              </p>
              <select
                value={person.role}
                disabled={busy}
                onChange={(event) => runAction(() => changeUserRole(userId, event.target.value))}
                style={{ ...inputStyle, marginTop: "0.7rem" }}
              >
                {ROLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.6rem", flexWrap: "wrap" }}>
                <button type="button" disabled={busy} onClick={() => runAction(() => setUserBlocked(userId, !person.is_blocked))}>
                  {person.is_blocked ? "Разблокировать" : "Заблокировать"}
                </button>
                <button type="button" disabled={busy} onClick={() => runAction(() => setUserArchived(userId, !person.is_archived))}>
                  {person.is_archived ? "Вернуть из архива" : "В архив"}
                </button>
              </div>
            </Card>
          )}

          {person.can_manage_permissions && (
            <Card>
              <strong>Права участника</strong>
              <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                Каждое право выдаётся отдельно. Перед включением видно, что именно человек сможет делать.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem", marginTop: "0.75rem" }}>
                {Object.entries(person.permissions).map(([permission, enabled]) => (
                  <div
                    key={permission}
                    style={{
                      padding: "0.75rem",
                      border: `1px solid ${enabled ? "var(--era-gold)" : "var(--era-border)"}`,
                      borderRadius: "0.85rem",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
                      <div>
                        <strong style={{ fontSize: "0.875rem" }}>{PERMISSION_LABELS[permission] ?? permission}</strong>
                        <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.75rem", lineHeight: 1.45 }}>
                          {PERMISSION_DESCRIPTIONS[permission] ?? "Дополнительное управленческое право."}
                        </p>
                      </div>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => runAction(() => toggleUserPermission(userId, permission))}
                        className={enabled ? "era-btn-primary" : undefined}
                        style={{ flexShrink: 0 }}
                      >
                        {enabled ? "Выдано" : "Выдать"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {person.can_award_points && (
            <Card>
              <strong>Баллы</strong>
              {person.points_suggestion && (
                <div style={{ marginTop: "0.7rem", padding: "0.8rem", borderRadius: "0.85rem", border: "1px solid var(--era-gold)", background: "var(--era-bg)" }}>
                  <span style={{ fontSize: "0.75rem", fontWeight: 800, textTransform: "uppercase", color: "var(--era-text-muted)" }}>Система предлагает</span>
                  <p style={{ margin: "0.3rem 0 0", fontWeight: 800 }}>+{person.points_suggestion.amount} баллов</p>
                  <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem" }}>{person.points_suggestion.reason}</p>
                  <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.75rem" }}>{person.points_suggestion.evidence.join(" · ")}</p>
                  <button
                    type="button"
                    className="era-btn-primary"
                    disabled={busy}
                    onClick={() => {
                      if (!confirmLargeManualAward(person.points_suggestion!.amount)) return;
                      runAction(() =>
                        awardUserPoints(
                          userId,
                          person.points_suggestion!.amount,
                          person.points_suggestion!.reason,
                          isLargeManualAward(person.points_suggestion!.amount),
                        ),
                      );
                    }}
                    style={{ marginTop: "0.6rem" }}
                  >
                    Начислить предложенные баллы
                  </button>
                </div>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "minmax(6rem, .7fr) minmax(0, 1.6fr)", gap: "0.5rem", marginTop: "0.75rem" }}>
                <input type="number" placeholder="± баллы" value={pointsAmount} onChange={(event) => setPointsAmount(event.target.value)} style={inputStyle} />
                <input type="text" placeholder="Причина ручной корректировки" value={pointsReason} onChange={(event) => setPointsReason(event.target.value)} style={inputStyle} />
              </div>
              <button
                type="button"
                className="era-btn-primary"
                disabled={busy || !pointsAmount || !pointsReason.trim()}
                onClick={() => {
                  const amount = Number(pointsAmount);
                  if (!confirmLargeManualAward(amount)) return;
                  runAction(async () => {
                    await awardUserPoints(userId, amount, pointsReason.trim(), isLargeManualAward(amount));
                    setPointsAmount("");
                    setPointsReason("");
                  });
                }}
                style={{ marginTop: "0.55rem" }}
              >
                Применить вручную
              </button>
            </Card>
          )}

          {person.can_award_points && (
            <Card>
              <strong>Знаки отличия</strong>
              {ownedBadges.length > 0 ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.55rem", marginTop: "0.7rem" }}>
                  {ownedBadges.map((badge) => (
                    <div key={badge.id} style={{ padding: "0.75rem", border: "1px solid var(--era-border)", borderRadius: "0.85rem" }}>
                      <span style={{ fontSize: "1rem" }}>✦</span> <strong style={{ fontSize: "0.8125rem" }}>{badge.name}</strong>
                      {badge.reason && <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "0.72rem", lineHeight: 1.4 }}>{badge.reason}</p>}
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>Знаков отличия пока нет.</p>
              )}

              {person.badge_suggestions.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--era-text-muted)", textTransform: "uppercase" }}>Рекомендации системы</span>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem", marginTop: "0.45rem" }}>
                    {person.badge_suggestions.map((suggestion) => (
                      <div key={suggestion.badge_id} style={{ padding: "0.8rem", border: "1px solid var(--era-gold)", borderRadius: "0.85rem" }}>
                        <strong>✦ {suggestion.badge_name}</strong>
                        <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem" }}>{suggestion.reason}</p>
                        <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.75rem" }}>{suggestion.evidence.join(" · ")}</p>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => runAction(() => awardUserBadge(userId, suggestion.badge_id, suggestion.reason))}
                          style={{ marginTop: "0.55rem" }}
                        >
                          Выдать знак
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {availableBadges.length > 0 && (
                <div style={{ marginTop: "1rem", paddingTop: "0.8rem", borderTop: "1px solid var(--era-border)" }}>
                  <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--era-text-muted)", textTransform: "uppercase" }}>Ручная выдача</span>
                  <select value={selectedBadgeId} onChange={(event) => setSelectedBadgeId(event.target.value)} style={{ ...inputStyle, marginTop: "0.5rem" }}>
                    <option value="">Выберите знак отличия</option>
                    {availableBadges.map((badge) => <option key={badge.id} value={badge.id}>{badge.name}</option>)}
                  </select>
                  {selectedBadge && (
                    <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.75rem" }}>
                      {selectedBadge.description || BADGE_DESCRIPTIONS[selectedBadge.name] || "Знак за подтверждённый вклад участника."}
                    </p>
                  )}
                  <input
                    type="text"
                    placeholder="За что выдаём этот знак?"
                    value={badgeReason}
                    onChange={(event) => setBadgeReason(event.target.value)}
                    style={{ ...inputStyle, marginTop: "0.5rem" }}
                  />
                  <button
                    type="button"
                    className="era-btn-primary"
                    disabled={busy || !selectedBadge || !badgeReason.trim()}
                    onClick={() => selectedBadge && runAction(async () => {
                      await awardUserBadge(userId, selectedBadge.id, badgeReason.trim());
                      setSelectedBadgeId("");
                      setBadgeReason("");
                    })}
                    style={{ marginTop: "0.5rem" }}
                  >
                    Выдать выбранный знак
                  </button>
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
