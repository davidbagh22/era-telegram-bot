import { useState } from "react";
import { PillTabs } from "../../components/PillTabs";
import { ActivitySubmissionsPanel } from "./events/ActivitySubmissionsPanel";
import { EventActivitiesPanel } from "./events/EventActivitiesPanel";
import { EventModerationPanel } from "./events/EventModerationPanel";
import { EventParticipantsPanel } from "./events/EventParticipantsPanel";
import { EventsList } from "./events/EventsList";

type EventsSection = "moderation" | "operations" | "activities";
type ActivitiesMode = "review" | "manage";

const SECTIONS: { value: EventsSection; label: string }[] = [
  { value: "moderation", label: "На рассмотрении" },
  { value: "operations", label: "Мероприятия" },
  { value: "activities", label: "Активности" },
];

export function AdminEventsScreen() {
  const [section, setSection] = useState<EventsSection>("moderation");
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [activitiesMode, setActivitiesMode] = useState<ActivitiesMode>("review");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs
        options={SECTIONS}
        active={section}
        onChange={(value) => {
          setSection(value);
          setSelectedEventId(null);
          setActivitiesMode("review");
        }}
      />
      {section === "moderation" && <EventModerationPanel />}
      {section === "operations" &&
        (selectedEventId === null ? (
          <EventsList onSelect={setSelectedEventId} />
        ) : (
          <EventParticipantsPanel eventId={selectedEventId} onBack={() => setSelectedEventId(null)} />
        ))}
      {section === "activities" &&
        (activitiesMode === "manage" && selectedEventId !== null ? (
          <EventActivitiesPanel
            eventId={selectedEventId}
            onBack={() => {
              setSelectedEventId(null);
              setActivitiesMode("review");
            }}
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <PillTabs
              options={[
                { value: "review", label: "На проверке" },
                { value: "manage", label: "Создать / отправить" },
              ]}
              active={activitiesMode}
              onChange={(value) => setActivitiesMode(value as ActivitiesMode)}
            />
            {activitiesMode === "review" && <ActivitySubmissionsPanel />}
            {activitiesMode === "manage" && <EventsList onSelect={setSelectedEventId} />}
          </div>
        ))}
    </div>
  );
}
