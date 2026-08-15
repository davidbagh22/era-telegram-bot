import { useEffect, useState } from "react";
import { AdminEventOperationsPanel } from "./AdminEventOperationsPanel";
import { AdminEventModerationPanel } from "./AdminEventModerationPanel";
import { AdminEventActivitiesPanel } from "./AdminEventActivitiesPanel";
import { SuggestedEventCreatePanel } from "./events/SuggestedEventCreatePanel";

const ACCENT = "#E32636";
type EventsSection = "create" | "moderation" | "operations" | "activities";

function ActionCell({
  symbol,
  title,
  caption,
  onClick,
}: {
  symbol: string;
  title: string;
  caption: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        all: "unset",
        boxSizing: "border-box",
        cursor: "pointer",
        minHeight: 130,
        borderRadius: 20,
        padding: "1rem",
        border: "1px solid var(--era-border)",
        background: "var(--era-surface)",
        boxShadow: "var(--era-shadow-soft)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 36,
          height: 36,
          borderRadius: 12,
          display: "grid",
          placeItems: "center",
          background: "var(--era-tint-red)",
          color: ACCENT,
          fontSize: "1.05rem",
          fontWeight: 900,
        }}
      >
        {symbol}
      </span>
      <span>
        <strong style={{ display: "block", fontSize: "1rem", lineHeight: 1.2 }}>{title}</strong>
        <span style={{ display: "block", marginTop: 4, color: "var(--era-text-muted)", fontSize: "0.75rem", lineHeight: 1.35 }}>{caption}</span>
      </span>
    </button>
  );
}

interface AdminEventsScreenProps {
  initialEventId?: number | null;
  initialCreateTopic?: string | null;
  onCreateTopicConsumed?: () => void;
}

export function AdminEventsScreen({
  initialEventId = null,
  initialCreateTopic = null,
  onCreateTopicConsumed,
}: AdminEventsScreenProps) {
  const [section, setSection] = useState<EventsSection | null>(
    initialEventId ? "operations" : initialCreateTopic ? "create" : null,
  );
  const [createTopic, setCreateTopic] = useState<string | null>(initialCreateTopic);

  useEffect(() => {
    if (initialEventId) setSection("operations");
  }, [initialEventId]);

  useEffect(() => {
    if (!initialCreateTopic?.trim()) return;
    setCreateTopic(initialCreateTopic.trim());
    setSection("create");
  }, [initialCreateTopic]);

  const handlePrepared = () => {
    setCreateTopic(null);
    onCreateTopicConsumed?.();
  };

  if (section) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
        <button
          type="button"
          onClick={() => setSection(null)}
          style={{
            alignSelf: "flex-start",
            minHeight: 44,
            padding: "0.5rem 0.75rem",
            borderRadius: 14,
            background: "var(--era-surface)",
            border: "1px solid var(--era-border)",
            color: "var(--era-text)",
            fontWeight: 800,
          }}
        >
          ← События
        </button>

        {section === "create" && (
          <SuggestedEventCreatePanel suggestedTopic={createTopic} onPrepared={handlePrepared} />
        )}
        {section === "moderation" && <AdminEventModerationPanel />}
        {section === "operations" && <AdminEventOperationsPanel initialEventId={initialEventId} />}
        {section === "activities" && <AdminEventActivitiesPanel />}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <header>
        <p className="era-kicker">Управление событиями</p>
        <h2 style={{ margin: "0.25rem 0 0", fontSize: "var(--era-text-2xl)", letterSpacing: "-0.03em" }}>События</h2>
        <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-muted)", maxWidth: 560 }}>
          От создания до посещаемости, баллов и результатов — каждый блок ведёт к реальному действию.
        </p>
      </header>

      <div className="era-grid-2">
        <ActionCell symbol="＋" title="Создать" caption="Новый черновик мероприятия" onClick={() => setSection("create")} />
        <ActionCell symbol="✓" title="Модерация" caption="Проверка и публикация" onClick={() => setSection("moderation")} />
        <ActionCell symbol="◎" title="Участники" caption="Регистрации, посещение, экспорт" onClick={() => setSection("operations")} />
        <ActionCell symbol="✦" title="Активности" caption="Задания и баллы после события" onClick={() => setSection("activities")} />
      </div>
    </div>
  );
}
