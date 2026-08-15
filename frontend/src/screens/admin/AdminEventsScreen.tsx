import { useState } from "react";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { ActivitySubmissionsPanel } from "./events/ActivitySubmissionsPanel";
import { AdminEventCreatePanel } from "./events/AdminEventCreatePanel";
import { EventActivitiesPanel } from "./events/EventActivitiesPanel";
import { EventModerationPanel } from "./events/EventModerationPanel";
import { EventParticipantsPanel } from "./events/EventParticipantsPanel";
import { EventsList } from "./events/EventsList";

export type EventsSection = "create" | "moderation" | "operations" | "activities";
type ActivitiesMode = "review" | "manage";

const SECTIONS: { value: EventsSection; label: string; description: string; icon: string; step: string }[] = [
  { value: "create", label: "Создать мероприятие", description: "Название, дата, место, лимит и публикация", icon: "＋", step: "СТАРТ" },
  { value: "moderation", label: "Проверить предложения", description: "События, которые команда отправила на согласование", icon: "✓", step: "02" },
  { value: "operations", label: "Вести участников", description: "Регистрации, посещаемость, баллы и списки", icon: "◎", step: "03" },
  { value: "activities", label: "Добавить активности", description: "Задания после события и проверка результатов", icon: "✦", step: "04" },
];

interface AdminEventsScreenProps {
  initialSection?: EventsSection | null;
}

export function AdminEventsScreen({ initialSection = null }: AdminEventsScreenProps) {
  const [section, setSection] = useState<EventsSection | null>(initialSection);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [activitiesMode, setActivitiesMode] = useState<ActivitiesMode | null>(null);

  const backToMenu = () => {
    setSection(null);
    setSelectedEventId(null);
    setActivitiesMode(null);
  };

  if (!section) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <Card gradient>
          <p style={{ margin: "0 0 0.25rem", color: "rgba(255,255,255,0.72)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Мероприятия · полный цикл</p>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>От идеи до результата</h2>
          <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.86)", lineHeight: 1.45 }}>
            Выберите действие. Для нового события начинайте с первой карточки — дальше система сама ведёт по этапам.
          </p>
        </Card>
        {SECTIONS.map((item) => (
          <div key={item.value} style={{ position: "relative" }}>
            <span style={{ position: "absolute", zIndex: 2, right: "0.8rem", top: "0.7rem", fontSize: "0.65rem", fontWeight: 900, color: item.value === "create" ? "var(--era-red)" : "var(--era-text-muted)", letterSpacing: "0.08em" }}>{item.step}</span>
            <ActionCell title={item.label} description={item.description} leading={item.icon} onClick={() => setSection(item.value)} />
          </div>
        ))}
      </div>
    );
  }

  const current = SECTIONS.find((item) => item.value === section);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={backToMenu} style={{ alignSelf: "flex-start" }}>← К этапам мероприятий</button>
      <div>
        <p style={{ margin: "0 0 0.2rem", color: "var(--era-red)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Мероприятия · {current?.step}</p>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{current?.label}</h2>
        <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{current?.description}</p>
      </div>

      {section === "create" && <AdminEventCreatePanel />}
      {section === "moderation" && <EventModerationPanel />}
      {section === "operations" && (
        selectedEventId === null ? <EventsList onSelect={setSelectedEventId} /> : <EventParticipantsPanel eventId={selectedEventId} onBack={() => setSelectedEventId(null)} />
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
