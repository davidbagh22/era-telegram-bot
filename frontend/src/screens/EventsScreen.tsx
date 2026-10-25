import { EditorialHero } from "../components/EditorialHero";
import { EventIcon } from "../components/icons";
import { MediaRequestButton } from "../components/MediaRequestButton";
import { EventsTab } from "./activity/EventsTab";

interface EventsScreenProps {
  initialItemId?: number | null;
}

export function EventsScreen({ initialItemId = null }: EventsScreenProps) {
  const isDetail = initialItemId !== null;
  return (
    <div
      className="era-page"
      style={{
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      {!isDetail && (
        <EditorialHero
          eyebrow="Здесь начинается движение"
          title="События"
          description="Выбирайте формат, смотрите программу и занимайте место в один шаг."
          glow="cool"
        >
          <span
            aria-hidden="true"
            style={{
              width: 42,
              height: 42,
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--era-tint-violet)",
              color: "var(--era-violet)",
            }}
          >
            <EventIcon width={21} height={21} />
          </span>
        </EditorialHero>
      )}

      {initialItemId !== null ? <MediaRequestButton sourceType="event" sourceId={initialItemId} /> : null}

      <section style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {!isDetail && <h2 style={{ fontSize: "var(--era-text-xl)", margin: 0 }}>Ближайшее</h2>}
        <EventsTab initialItemId={initialItemId} />
      </section>
    </div>
  );
}
