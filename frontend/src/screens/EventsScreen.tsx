import { Card } from "../components/Card";
import { EventIcon } from "../components/icons";
import { EventsTab } from "./activity/EventsTab";

interface EventsScreenProps {
  initialItemId?: number | null;
}

export function EventsScreen({ initialItemId = null }: EventsScreenProps) {
  return (
    <div
      className="era-page"
      style={{
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <Card gradient style={{ position: "relative", overflow: "hidden", minHeight: 148 }}>
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
        <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <span
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "rgba(255,255,255,0.14)",
            }}
            aria-hidden="true"
          >
            <EventIcon width={22} height={22} />
          </span>
          <div>
            <p
              style={{
                margin: "0 0 0.35rem",
                color: "rgba(255,255,255,0.68)",
                fontSize: "var(--era-text-xs)",
                fontWeight: 800,
                textTransform: "uppercase",
              }}
            >
              Афиша ЭРА
            </p>
            <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)", lineHeight: 1.08 }}>
              События
            </h1>
            <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.78)", maxWidth: 260 }}>
              Регистрация, ближайшие встречи и активности после мероприятий.
            </p>
          </div>
        </div>
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: 0 }}>Мероприятия</h2>
        <EventsTab initialItemId={initialItemId} />
      </section>
    </div>
  );
}
