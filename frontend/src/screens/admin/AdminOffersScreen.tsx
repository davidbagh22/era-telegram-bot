import { useState } from "react";
import { PillTabs } from "../../components/PillTabs";
import { OfferApplicationsPanel } from "./offers/OfferApplicationsPanel";
import { OffersPanel } from "./offers/OffersPanel";
import { PartnersPanel } from "./offers/PartnersPanel";

type OffersSection = "applications" | "offers" | "partners";

const SECTIONS: { value: OffersSection; label: string }[] = [
  { value: "applications", label: "Заявки" },
  { value: "offers", label: "Предложения" },
  { value: "partners", label: "Партнёры" },
];

export function AdminOffersScreen() {
  const [section, setSection] = useState<OffersSection>("applications");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "applications" && <OfferApplicationsPanel />}
      {section === "offers" && <OffersPanel />}
      {section === "partners" && <PartnersPanel />}
    </div>
  );
}
