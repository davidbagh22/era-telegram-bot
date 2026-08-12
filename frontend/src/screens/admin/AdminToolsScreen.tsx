import { useState } from "react";
import { PillTabs } from "../../components/PillTabs";
import { BroadcastPanel } from "./tools/BroadcastPanel";
import { ContactsPanel } from "./tools/ContactsPanel";
import { GoalsPanel } from "./tools/GoalsPanel";
import { GreetingsPanel } from "./tools/GreetingsPanel";
import { StructurePanel } from "./tools/StructurePanel";

type ToolsSection = "goals" | "contacts" | "structure" | "greetings" | "broadcast";

const SECTIONS: { value: ToolsSection; label: string }[] = [
  { value: "goals", label: "Цели месяца" },
  { value: "contacts", label: "Организации" },
  { value: "structure", label: "Структура" },
  { value: "greetings", label: "Приветствия" },
  { value: "broadcast", label: "Рассылки" },
];

// Groups the smaller admin-panel ports (monthly goals, organization
// contacts, department structure, chat greetings) into one Mini App
// section — see docs/BOT_VS_MINIAPP_AUDIT.md for the full porting scope.
export function AdminToolsScreen() {
  const [section, setSection] = useState<ToolsSection>("goals");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "goals" && <GoalsPanel />}
      {section === "contacts" && <ContactsPanel />}
      {section === "structure" && <StructurePanel />}
      {section === "greetings" && <GreetingsPanel />}
      {section === "broadcast" && <BroadcastPanel />}
    </div>
  );
}
