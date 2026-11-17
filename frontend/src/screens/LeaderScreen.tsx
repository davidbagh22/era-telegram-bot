import { useState } from "react";
import { ActionCell } from "../components/ActionCell";
import { ActivitiesTab } from "./leader/ActivitiesTab";
import { OpenTasksTab } from "./leader/OpenTasksTab";
import { OverviewTab } from "./leader/OverviewTab";
import { WeeklyPulseTab } from "./leader/WeeklyPulseTab";

type LeaderSection = "overview" | "weekly-pulse" | "open-tasks" | "activities";

const SECTIONS: { value: LeaderSection; label: string; description: string }[] = [
  { value: "overview", label: "Моя команда", description: "Состояние зоны и кто в контуре" },
  { value: "open-tasks", label: "Задачи на проверке", description: "Что требует решения прямо сейчас" },
  { value: "weekly-pulse", label: "Пульс недели", description: "Короткий отчёт: факты и следующий шаг" },
  { value: "activities", label: "Активности", description: "Проекты, события и работа участников" },
];

export function LeaderScreen() {
  const [section, setSection] = useState<LeaderSection | null>(null);

  if (section) {
    const current = SECTIONS.find((item) => item.value === section);
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <button type="button" onClick={() => setSection(null)} style={{ alignSelf: "flex-start" }}>
          ← Назад
        </button>
        <div>
          <p style={{ margin: "0 0 0.25rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
            Режим лидера
          </p>
          <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)", margin: 0 }}>
            {current?.label}
          </h1>
        </div>
        {section === "overview" && <OverviewTab />}
        {section === "weekly-pulse" && <WeeklyPulseTab />}
        {section === "open-tasks" && <OpenTasksTab />}
        {section === "activities" && <ActivitiesTab />}
      </div>
    );
  }

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div>
        <p style={{ margin: "0 0 0.25rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Управление своей зоной
        </p>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-3xl)", margin: 0 }}>
          Режим лидера
        </h1>
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>
          Команда, проверка задач, пульс и активности — без лишнего шума.
        </p>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
        {SECTIONS.map((item) => (
          <ActionCell
            key={item.value}
            title={item.label}
            description={item.description}
            onClick={() => setSection(item.value)}
          />
        ))}
        <ActionCell
          title="Медиа-запрос"
          description="Пакет (фото / рилс / полный) и срок для команды Медиа"
          onClick={() => {
            window.location.hash = "#/media";
          }}
        />
      </div>
    </div>
  );
}
