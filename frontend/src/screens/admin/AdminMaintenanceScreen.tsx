import { useCallback, useState } from "react";
import {
  describeActionError,
  fetchAdminDashboard,
  fetchMaintenancePreview,
  runMaintenanceReset,
} from "../../api/client";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";

export type MaintenanceTarget =
  | "applications"
  | "participants"
  | "development"
  | "career"
  | "offices"
  | "projects"
  | "events"
  | "tasks"
  | "offers"
  | "data-rights"
  | "surveys"
  | "analytics"
  | "system"
  | "tools";

interface AdminMaintenanceScreenProps {
  onOpen: (target: MaintenanceTarget) => void;
}

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

const COUNT_LABELS: Record<string, string> = {
  users: "участников",
  events: "мероприятий",
  projects: "проектов",
  tasks: "заданий",
  points: "операций с баллами",
  portfolio_items: "записей портфолио",
  broadcasts: "рассылок",
  user_questions: "вопросов",
  audit_logs: "технических записей",
};

function QueueAction({
  title,
  description,
  count,
  onClick,
}: {
  title: string;
  description: string;
  count?: number;
  onClick: () => void;
}) {
  return (
    <div style={{ position: "relative" }}>
      <ActionCell title={title} description={description} onClick={onClick} />
      {count !== undefined && count > 0 && (
        <div style={{ position: "absolute", right: "2.5rem", top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
          <StatusBadge label={String(count)} tone="red" />
        </div>
      )}
    </div>
  );
}

export function AdminMaintenanceScreen({ onOpen }: AdminMaintenanceScreenProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const dashboard = useAsync(() => fetchAdminDashboard(), [refreshKey]);
  const resetState = useAsync(() => fetchMaintenancePreview(), [refreshKey]);
  const [confirming, setConfirming] = useState(false);
  const [phraseInput, setPhraseInput] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleReset = useCallback(async () => {
    if (resetState.status !== "ready") return;
    setRunning(true);
    setError(null);
    try {
      const outcome = await runMaintenanceReset(phraseInput);
      setResult(`Готово — удалено ${outcome.total} связанных тестовых записей.`);
      setConfirming(false);
      setPhraseInput("");
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setRunning(false);
    }
  }, [phraseInput, resetState]);

  const metrics = dashboard.status === "ready" ? dashboard.data.metrics : {};
  const taskQueue = (metrics.task_results ?? 0) + (metrics.activity_results ?? 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <Card
        style={{
          overflow: "hidden",
          background: "radial-gradient(circle at 90% 0%, rgba(99,44,255,.16), transparent 42%), var(--era-surface)",
        }}
      >
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Операционный центр
        </p>
        <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-2xl)" }}>Обслуживание ЭРА</h2>
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>
          Ежедневная работа администратора собрана здесь. Нажатие ведёт прямо в нужный рабочий экран Mini App — без возврата в бот и без поиска раздела по меню.
        </p>
        {dashboard.status === "ready" && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: "0.8rem" }}>
            <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Решений на очереди</span>
            <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.8rem" }}>{dashboard.data.attention_total}</strong>
          </div>
        )}
      </Card>

      <section>
        <h3 style={{ margin: "0 0 0.55rem" }}>Разобрать очередь</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <QueueAction title="Новые заявки" description="Одобрить, запросить данные или отклонить" count={metrics.users_pending} onClick={() => onOpen("applications")} />
          <QueueAction title="Проекты на проверке" description="Решения по проектной воронке" count={metrics.projects_review} onClick={() => onOpen("projects")} />
          <QueueAction title="Мероприятия на согласовании" description="Проверить, опубликовать, начать и завершить событие" count={metrics.events_pending} onClick={() => onOpen("events")} />
          <QueueAction title="Результаты заданий и активностей" description="Принять, вернуть на доработку или отклонить" count={taskQueue} onClick={() => onOpen("tasks")} />
          <QueueAction title="Возможности и награды" description="Партнёрские предложения, заявки и выдача" count={metrics.rewards} onClick={() => onOpen("offers")} />
          <QueueAction title="Портфолио и рекомендации" description="Подтвердить достижения и официальные рекомендательные письма" onClick={() => onOpen("career")} />
          <QueueAction title="Данные и права" description="Запросы на экспорт, удаление и анонимизацию" onClick={() => onOpen("data-rights")} />
        </div>
      </section>

      <section>
        <h3 style={{ margin: "0 0 0.55rem" }}>Люди и развитие</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <QueueAction title="Участники" description={`База, роли и статусы${metrics.users_total !== undefined ? ` · ${metrics.users_total}` : ""}`} onClick={() => onOpen("participants")} />
          <QueueAction title="Состояние и развитие" description="Безопасные сводки «Моего вектора», охват Check-in и потребности" onClick={() => onOpen("development")} />
          <QueueAction title="Должности и структура" description="Роли, руководители и организационная структура" onClick={() => onOpen("offices")} />
        </div>
      </section>

      <section>
        <h3 style={{ margin: "0 0 0.55rem" }}>Коммуникация</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <QueueAction title="Опросы и обратная связь" description="Создать опрос, посмотреть ответы и понять реакцию сообщества" onClick={() => onOpen("surveys")} />
          <QueueAction title="Центр связи" description="Чаты, FAQ, приветствия, рассылки и автоконтент" onClick={() => onOpen("tools")} />
        </div>
      </section>

      <section>
        <h3 style={{ margin: "0 0 0.55rem" }}>Контроль</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <QueueAction title="Аналитика и здоровье организации" description="Эффективность, Пульс, рост, удержание, события, проекты, возможности и Excel" onClick={() => onOpen("analytics")} />
          <QueueAction title="Состояние платформы" description="Диагностика, инциденты, резервные копии и техническое здоровье" onClick={() => onOpen("system")} />
        </div>
      </section>

      <Card style={{ padding: "0.85rem 0.9rem", borderLeft: "3px solid var(--era-gold-ink)" }}>
        <strong>Что остаётся в Telegram</strong>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)", lineHeight: 1.45 }}>
          Только действия, которым нужен сам Telegram-контекст: первичная привязка чатов и аварийный резервный сценарий. Проекты, события, заявки, люди, аналитика, портфолио, опросы и коммуникации управляются в приложении.
        </p>
      </Card>

      <section style={{ marginTop: "0.35rem" }}>
        <p style={{ margin: "0 0 0.25rem", color: "var(--era-error)", fontSize: "var(--era-text-xs)", fontWeight: 850, textTransform: "uppercase" }}>Опасная зона</p>
        <h3 style={{ margin: "0 0 0.55rem" }}>Очистка тестовых данных</h3>

        {resetState.status === "loading" && <Card>Проверяем доступ…</Card>}
        {resetState.status === "error" && (
          <Card>
            <strong>Ограничено</strong>
            <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
              Разрушительная очистка по-прежнему доступна только основному администратору. Остальные функции обслуживания выше работают независимо.
            </p>
          </Card>
        )}
        {resetState.status === "ready" && (() => {
          const { counts, total, confirmation_phrase: confirmationPhrase } = resetState.data;
          const visible = Object.entries(counts).filter(([name]) => name in COUNT_LABELS);
          return (
            <Card>
              <strong>Удалить тестовую операционную историю</strong>
              <p style={{ margin: "0.5rem 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                {visible.length > 0 ? visible.map(([name, value]) => `${COUNT_LABELS[name]}: ${value}`).join(" · ") : "Рабочих данных для удаления нет"}
              </p>
              <p style={{ margin: "0 0 0.75rem" }}>Всего связанных записей: {total}</p>
              <p style={{ margin: "0 0 0.75rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                Будут сохранены: основной администратор, департаменты, направления, бейджи, должности, ссылки, ID чатов и тексты приветствий.
              </p>

              {error && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: "0 0 0.75rem" }}>{error}</p>}
              {result && <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", margin: "0 0 0.75rem" }}>{result}</p>}

              {!confirming ? (
                <button type="button" disabled={total === 0} onClick={() => setConfirming(true)}>Продолжить очистку</button>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  <p style={{ margin: 0, color: "var(--era-error)", fontWeight: 600 }}>Это действие нельзя отменить</p>
                  <p style={{ margin: 0 }}>Чтобы удалить тестовых участников и всю рабочую историю, напишите точно:<br /><strong>{confirmationPhrase}</strong></p>
                  <input value={phraseInput} onChange={(e) => setPhraseInput(e.target.value)} placeholder={confirmationPhrase} style={inputStyle} />
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button type="button" disabled={running || phraseInput !== confirmationPhrase} onClick={handleReset}>Подтвердить и удалить</button>
                    <button type="button" disabled={running} onClick={() => { setConfirming(false); setPhraseInput(""); }}>Отмена</button>
                  </div>
                </div>
              )}
            </Card>
          );
        })()}
      </section>
    </div>
  );
}
