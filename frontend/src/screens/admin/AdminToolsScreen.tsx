import { useState } from "react";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { AutoContentPanel } from "./tools/AutoContentPanel";
import { BroadcastPanel } from "./tools/BroadcastPanel";
import { ChatsPanel } from "./tools/ChatsPanel";
import { ContactsPanel } from "./tools/ContactsPanel";
import { GoalsPanel } from "./tools/GoalsPanel";
import { GreetingsPanel } from "./tools/GreetingsPanel";
import { StructurePanel } from "./tools/StructurePanel";

type ToolsSection = "goals" | "contacts" | "structure" | "chats" | "greetings" | "broadcast" | "autocontent";
type ToolGroup = "team" | "communication";

const SECTIONS: { value: ToolsSection; group: ToolGroup; label: string; description: string; icon: string }[] = [
  { value: "goals", group: "team", label: "Цели месяца", description: "Что команда должна довести до результата сейчас", icon: "◎" },
  { value: "contacts", group: "team", label: "Организации", description: "Партнёры, контакты и рабочие отношения ЭРА", icon: "◇" },
  { value: "structure", group: "team", label: "Структура", description: "Департаменты, направления и устройство команды", icon: "⌘" },
  { value: "chats", group: "communication", label: "Чаты", description: "Привязка, доступ, FAQ и техническое состояние", icon: "#" },
  { value: "greetings", group: "communication", label: "Приветствия", description: "Как ЭРА встречает новых участников в рабочих чатах", icon: "✦" },
  { value: "broadcast", group: "communication", label: "Рассылки", description: "Личные сообщения и выбранные организационные чаты", icon: "↗" },
  { value: "autocontent", group: "communication", label: "Автоконтент", description: "09:00, 18:00, вызовы недели, темы месяца и праздники", icon: "◉" },
];

const GROUP_LABELS: Record<ToolGroup, { title: string; description: string }> = {
  team: { title: "Команда", description: "Фокус, партнёры и устройство ЭРА" },
  communication: { title: "Коммуникации", description: "Что, кому и где говорит ЭРА" },
};

export function AdminToolsScreen() {
  const [section, setSection] = useState<ToolsSection | null>(null);

  if (!section) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
        <Card gradient style={{ position: "relative", overflow: "hidden", minHeight: 166 }}>
          <div aria-hidden="true" style={{ position: "absolute", width: 190, height: 190, borderRadius: "50%", right: -72, top: -76, background: "radial-gradient(circle, rgba(255,255,255,0.28), rgba(255,255,255,0.02) 66%, transparent 70%)" }} />
          <div style={{ position: "relative" }}>
            <p style={{ margin: "0 0 0.3rem", color: "rgba(255,255,255,0.72)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Центр связи</p>
            <h2 style={{ margin: 0, fontSize: "var(--era-text-3xl)", lineHeight: 1.05 }}>Управляйте голосом ЭРА</h2>
            <p style={{ margin: "0.6rem 0 0", maxWidth: 310, color: "rgba(255,255,255,0.84)", lineHeight: 1.45 }}>
              Чаты, рассылки, приветствия и ежедневный ритм — в одном месте. Здесь видно не список настроек, а то, как организация общается с людьми.
            </p>
          </div>
        </Card>

        {(["team", "communication"] as ToolGroup[]).map((group) => (
          <section key={group}>
            <div style={{ marginBottom: "0.55rem" }}>
              <h3 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>{GROUP_LABELS[group].title}</h3>
              <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{GROUP_LABELS[group].description}</p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
              {SECTIONS.filter((item) => item.group === group).map((item) => (
                <ActionCell key={item.value} title={item.label} description={item.description} leading={item.icon} onClick={() => setSection(item.value)} />
              ))}
            </div>
          </section>
        ))}
      </div>
    );
  }

  const current = SECTIONS.find((item) => item.value === section);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
      <button type="button" onClick={() => setSection(null)} style={{ alignSelf: "flex-start" }}>← Центр связи</button>
      <div>
        <p style={{ margin: "0 0 0.2rem", color: "var(--era-red)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Центр связи</p>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{current?.label}</h2>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{current?.description}</p>
      </div>
      {section === "goals" && <GoalsPanel />}
      {section === "contacts" && <ContactsPanel />}
      {section === "structure" && <StructurePanel />}
      {section === "chats" && <ChatsPanel />}
      {section === "greetings" && <GreetingsPanel />}
      {section === "broadcast" && <BroadcastPanel />}
      {section === "autocontent" && <AutoContentPanel />}
    </div>
  );
}
