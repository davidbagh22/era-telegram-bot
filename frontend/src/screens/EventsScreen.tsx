import { Card } from "../components/Card";
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
        <Card gradient style={{ position: "relative", overflow: "hidden", minHeight: 142 }}>
          <div
            aria-hidden="true"
            style={{
              position: "absolute",
              right: -38,
              top: -42,
              width: 150,
              height: 150,
              borderRadius: "50%",
              border: "1px solid rgba(255,255,255,0.2)",
              background: "rgba(255,255,255,0.08)",
            }}
          />
          <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: "0.7rem" }}>
            <span
              style={{
                width: 42,
                height: 42,
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "rgba(255,255,255,0.14)",
              }}
              aria-hidden="true"
            >
              <EventIcon width={21} height={21} />
            </span>
            <div>
              <p style={{ margin: "0 0 0.3rem", color: "rgba(255,255,255,0.68)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
                Здесь начинается движение
              </p>
              <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)", lineHeight: 1.08 }}>События</h1>
              <p style={{ margin: "0.45rem 0 0", color: "rgba(255,255,255,0.78)", maxWidth: 290 }}>
                Выбирайте формат, смотрите программу и занимайте место в один шаг.
              </p>
            </div>
          </div>
        </Card>
      )}

      {initialItemId !== null ? <MediaRequestButton sourceType="event" sourceId={initialItemId} /> : null}

      <section style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {!isDetail && <h2 style={{ fontSize: "var(--era-text-xl)", margin: 0 }}>Ближайшее</h2>}
        <EventsTab initialItemId={initialItemId} />
      </section>
    </div>
  );
}
