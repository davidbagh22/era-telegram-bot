import { EditorialHero } from "../components/EditorialHero";
import { EventIcon } from "../components/icons";
import { EventsTab } from "./activity/EventsTab";

interface EventsScreenProps {
  canEdit?: boolean;
  initialItemId?: number | null;
  initialScope?: "mine";
}

export function EventsScreen({ initialItemId = null, initialScope, canEdit }: EventsScreenProps) {
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
        <>
          <EditorialHero
            eyebrow="Афиша ЭРА"
            title={initialScope === "mine" ? "Мои мероприятия" : "Афиша"}
            description="Ближайшие встречи и форматы. Запись — в один шаг."
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
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
              gap: "0.45rem",
            }}
          >
            <button
              type="button"
              className="era-btn-ghost"
              onClick={() => {
                if (window.location.hash !== "#/calendar") window.location.hash = "#/calendar";
              }}
              style={{ width: "100%", minHeight: 44, fontSize: "0.82rem" }}
            >
              Календарь
            </button>
            <button
              type="button"
              className="era-btn-ghost"
              onClick={() => {
                if (window.location.hash !== "#/tasks") window.location.hash = "#/tasks";
              }}
              style={{ width: "100%", minHeight: 44, fontSize: "0.82rem" }}
            >
              Задачи
            </button>
            <button
              type="button"
              className="era-btn-ghost"
              onClick={() => {
                if (window.location.hash !== "#/history") window.location.hash = "#/history";
              }}
              style={{ width: "100%", minHeight: 44, fontSize: "0.82rem" }}
            >
              История
            </button>
          </div>
        </>
      )}

      <section style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <EventsTab canEdit={canEdit} initialItemId={initialItemId} initialScope={initialScope} />
      </section>
    </div>
  );
}
