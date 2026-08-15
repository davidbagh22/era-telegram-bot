import { useEffect, useState } from "react";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { ActivitySubmissionsPanel } from "./events/ActivitySubmissionsPanel";
import { EventActivitiesPanel } from "./events/EventActivitiesPanel";
import { EventModerationPanel } from "./events/EventModerationPanel";
import { EventParticipantsPanel } from "./events/EventParticipantsPanel";
import { EventsList } from "./events/EventsList";
import { SuggestedEventCreatePanel } from "./events/SuggestedEventCreatePanel";

type EventsSection = "create" | "moderation" | "operations" | "activities";
type ActivitiesMode = "review" | "manage";

const SECTIONS: { value: EventsSection; label: string; description: string; icon: string }[] = [
  { value: "create", label: "Создать мероприятие", description: "10 шагов, автосохранение, афиша, напоминания и публикация", icon: "＋" },
  { value: "moderation", label: "На согласовании", description: "Проверить предложения мероприятий от команды", icon: "✓" },
  { value: "operations", label: "Участники и посещаемость", description: "Реальные регистрации, поиск, отметка присутствия и экспорт", icon: "◎" },
  { value: "activities", label: "Активности после события", description: "Задания, материалы, результаты и баллы участников", icon: "✦" },
];

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
  const [selectedEventId, setSelectedEventId] = useState<number | null>(initialEventId);
  const [activitiesMode, setActivitiesMode] = useState<ActivitiesMode | null>(null);
  const [createTopic, setCreateTopic] = useState<string | null>(initialCreateTopic);

  useEffect(() => {
    if (initialEventId) {
      setSection("operations");
      setSelectedEventId(initialEventId);
    }
  }, [initialEventId]);

  useEffect(() => {
    if (!initialCreateTopic?.trim()) return;
    setCreateTopic(initialCreateTopic.trim());
    setSection("create");
  }, [initialCreateTopic]);

  const backToMenu = () => {
    setSection(null);
    setSelectedEventId(null);
    setActivitiesMode(null);
    setCreateTopic(null);
    if (initialEventId) window.location.hash = "#/admin";
  };

  const handleSuggestedDraftPrepared = () => {
    setCreateTopic(null);
    onCreateTopicConsumed?.();
  };

  if (!section) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <Card style={{ borderColor: "rgba(227,38,54,.14)" }}>
          <p className="era-kicker">Управление событиями</p>
          <h2 style={{ margin: "0.3rem 0 0", fontSize: "var(--era-text-2xl)" }}>Полный цикл в одном месте</h2>
          <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>
            Создание → публикация → регистрации → посещаемость → активности → баллы. Каждый блок открывает реальные данные и действия.
          </p>
        </Card>
        {SECTIONS.map((item) => (
          <ActionCell key={item.value} title={item.label} description={item.description} leading={item.icon} onClick={() => setSection(item.value)} />
        ))}
      </div>
    );
  }

  const sectionMeta = SECTIONS.find((item) => item.value === section);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={backToMenu} style={{ alignSelf: "flex-start" }}>← К мероприятиям</button>
      <div>
        <p className="era-kicker">События</p>
        <h2 style={{ margin: "0.25rem 0 0", fontSize: "var(--era-text-2xl)" }}>{sectionMeta?.label}</h2>
        <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{sectionMeta?.description}</p>
      </div>

      {section === "create" && (
        <SuggestedEventCreatePanel suggestedTopic={createTopic} onPrepared={handleSuggestedDraftPrepared} />
      )}
      {section === "moderation" && <EventModerationPanel />}
      {section === "operations" && (
        selectedEventId === null
          ? <EventsList onSelect={setSelectedEventId} />
          : <EventParticipantsPanel eventId={selectedEventId} onBack={() => { setSelectedEventId(null); if (initialEventId) window.location.hash = "#/admin"; }} />
      )}
      {section === "activities" && activitiesMode === null && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <ActionCell title="Проверить результаты" description="Что участники уже отправили после мероприятий" leading="✓" onClick={() => setActivitiesMode("review")} />
          <ActionCell title="Создать активности" description="Выбрать мероприятие и добавить задания участникам" leading="＋" onClick={() => setActivitiesMode("manage")} />
        </div>
      )}
      {section === "activities" && activitiesMode === "review" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <button type="button" onClick={() => setActivitiesMode(null)} style={{ alignSelf: "flex-start" }}>← Назад</button>
          <ActivitySubmissionsPanel />
        </div>
      )}
      {section === "activities" && activitiesMode === "manage" && selectedEventId === null && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <button type="button" onClick={() => setActivitiesMode(null)} style={{ alignSelf: "flex-start" }}>← Назад</button>
          <EventsList onSelect={setSelectedEventId} />
        </div>
      )}
      {section === "activities" && activitiesMode === "manage" && selectedEventId !== null && (
        <EventActivitiesPanel eventId={selectedEventId} onBack={() => setSelectedEventId(null)} />
      )}
    </div>
  );
}
