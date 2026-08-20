import { useState } from "react";
import { PillTabs } from "../../components/PillTabs";
import { AuctionsPanel } from "./offers/AuctionsPanel";
import { OfferApplicationsPanel } from "./offers/OfferApplicationsPanel";
import { OffersPanel } from "./offers/OffersPanel";
import { PartnersPanel } from "./offers/PartnersPanel";
import { RewardsPanel } from "./offers/RewardsPanel";

export type OffersSection = "applications" | "offers" | "partners" | "auctions" | "rewards";

const SECTIONS: { value: OffersSection; label: string }[] = [
  { value: "applications", label: "Заявки" },
  { value: "offers", label: "Предложения" },
  { value: "partners", label: "Партнёры" },
  { value: "auctions", label: "Аукционы" },
  { value: "rewards", label: "Каталог" },
];

export function AdminOffersScreen({ initialSection = "applications" }: { initialSection?: OffersSection }) {
  const [section, setSection] = useState<OffersSection>(initialSection);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "applications" && <OfferApplicationsPanel />}
      {section === "offers" && <OffersPanel />}
      {section === "partners" && <PartnersPanel />}
      {section === "auctions" && <AuctionsPanel />}
      {section === "rewards" && <RewardsPanel />}
    </div>
  );
}
