import { PersonDetail as PersonDetailRich } from "./PersonDetailRich";
import { AdminDevelopmentProfileCard } from "./AdminDevelopmentProfileCard";

export function PersonDetail({ userId, onBack }: { userId: number; onBack: () => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <PersonDetailRich userId={userId} onBack={onBack} />
      <AdminDevelopmentProfileCard userId={userId} />
    </div>
  );
}
