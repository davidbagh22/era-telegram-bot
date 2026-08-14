import { useState } from "react";
import { ActionCell } from "../../components/ActionCell";
import { BroadcastPanel } from "./tools/BroadcastPanel";
import { ChatsPanel } from "./tools/ChatsPanel";
import { ContactsPanel } from "./tools/ContactsPanel";
import { GoalsPanel } from "./tools/GoalsPanel";
import { GreetingsPanel } from "./tools/GreetingsPanel";
import { StructurePanel } from "./tools/StructurePanel";
import { SystemPanel } from "./tools/SystemPanel";

type ToolsSection = "goals" | "contacts" | "structure" | "chats" | "greetings" | "broadcast" | "system";

const SECTIONS: { value: ToolsSection; label: string; description: string }[] = [
  { value: "goals", label: "Цели месяца", description: "Фокус команды и ключевые цели текущего месяца" },
  { value: "contacts", label: "Организации", description: "Партнёрские и рабочие контакты ЭРА" },
  { value: "structure", label: "Структура", description: "Департаменты, направления и организационная схема" },
  { value: "chats", label: "Чаты", description: "Привязка, доступ и состояние организационных чатов" },
  { value: "greetings", label: "Приветствия", description: "Сообщения для новых участников в чатах" },
  { value: "broadcast", label: "Рассылки", description: "Коммуникации с участниками и рабочими чатами" },
  { value: "system", label: "Система", description: "Health score, диагностика, инциденты и резервные копии" },
];

export function AdminToolsScreen() {
  const [section, setSection] = useState<ToolsSection | null>(null);

  if (!section) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
        {SECTIONS.map((item) => (
          <ActionCell
            key={item.value}
            title={item.label}
            description={item.description}
            onClick={() => setSection(item.value)}
          />
        ))}
      </div>
    );
  }

  const current = SECTIONS.find((item) => item.value === section);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
      <button type="button" onClick={() => setSection(null)} style={{ alignSelf: "flex-start" }}>
        ← Назад
      </button>
      <div>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{current?.label}</h2>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{current?.description}</p>
      </div>
      {section === "goals" && <GoalsPanel />}
      {section === "contacts" && <ContactsPanel />}
      {section === "structure" && <StructurePanel />}
      {section === "chats" && <ChatsPanel />}
      {section === "greetings" && <GreetingsPanel />}
      {section === "broadcast" && <BroadcastPanel />}
      {section === "system" && <SystemPanel />}
    </div>
  );
}
