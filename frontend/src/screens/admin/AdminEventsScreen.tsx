import { useState } from "react";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { ActivitySubmissionsPanel } from "./events/ActivitySubmissionsPanel";
import { AdminEventCreatePanel } from "./events/AdminEventCreatePanel";
import { EventActivitiesPanel } from "./events/EventActivitiesPanel";
import { EventModerationPanel } from "./events/EventModerationPanel";
import { EventParticipantsPanel } from "./events/EventParticipantsPanel";
import { EventsList } from "./events/EventsList";

type EventsSection = "create" | "moderation" | "operations" | "activities";
type ActivitiesMode = "review" | "manage";

const SECTIONS: { value: EventsSection; label: string; description: string; icon: string }[] = [
  { value: "create", label: "Создать мероприятие", description: "Черновик или сразу открыть регистрацию", icon: "＋" },
  { value: "moderation", label: "На согласовании", description: "Проверить предложения мероприятий от команды", icon: "✓" },
  { value: "operations", label: "Участники и посещаемость", description: "Регистрации, отметка присутствия и баллы", icon: "◎" },
  { value: "activities", label: "Активности после события", description: "Задания, материалы и результаты участников", icon: "✦" },
];

interface AdminEventsScreenProps {
  initialEventId?: number | null;
}

export function AdminEventsScreen({ initialEventId = null }: AdminEventsScreenProps) {
  const [section, setSection] = useState<EventsSection | null>(initialEventId ? "operations" : null);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(initialEventId);
  const [activitiesMode, setActivitiesMode] = useState<ActivitiesMode | null>(null);

  const backToMenu = () => {
    setSection(null);
    setSelectedEventId(null);
    setActivitiesMode(null);
    if (initialEventId) window.location.hash = "#/admin";
  };

  if (!section) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <Card gradient>
          <p style={{ margin: "0 0 0.25rem", color: "rgba(255,255,255,0.72)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Мероприятия</p>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Полный цикл в одном месте</h2>
          <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.82)" }}>
            Сначала создайте или согласуйте событие. После публикации здесь же ведите регистрации, посещаемость и активности.
          </p>
        </Card>
        {SECTIONS.map((item) => (
          <ActionCell key={item.value} title={item.label} description={item.description} leading={item.icon} onClick={() => setSection(item.value)} />
        ))}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={backToMenu} style={{ alignSelf: "flex-start" }}>← К мероприятиям</button>
      <div>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{SECTIONS.find((item) => item.value === section)?.label}</h2>
        <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{SECTIONS.find((item) => item.value === section)?.description}</p>
      </div>

      {section === "create" && <AdminEventCreatePanel />}
      {section === "moderation" && <EventModerationPanel />}
      {section === "operations" && (
        selectedEventId === null ? <EventsList onSelect={setSelectedEventId} /> : <EventParticipantsPanel eventId={selectedEventId} onBack={() => { setSelectedEventId(null); if (initialEventId) window.location.hash = "#/admin"; }} />
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