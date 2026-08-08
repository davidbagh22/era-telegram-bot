import { useState } from "react";
import { PillTabs } from "../../components/PillTabs";
import { EventModerationPanel } from "./events/EventModerationPanel";
import { EventParticipantsPanel } from "./events/EventParticipantsPanel";
import { EventsList } from "./events/EventsList";

type EventsSection = "moderation" | "operations";

const SECTIONS: { value: EventsSection; label: string }[] = [
  { value: "moderation", label: "На рассмотрении" },
  { value: "operations", label: "Мероприятия" },
];

export function AdminEventsScreen() {
  const [section, setSection] = useState<EventsSection>("moderation");
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs
        options={SECTIONS}
        active={section}
        onChange={(value) => {
          setSection(value);
          setSelectedEventId(null);
        }}
      />
      {section === "moderation" && <EventModerationPanel />}
      {section === "operations" &&
        (selectedEventId === null ? (
          <EventsList onSelect={setSelectedEventId} />
        ) : (
          <EventParticipantsPanel eventId={selectedEventId} onBack={() => setSelectedEventId(null)} />
        ))}
    </div>
  );
}
