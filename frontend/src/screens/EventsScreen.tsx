import { PageHeader } from "../components/PageHeader";
import { EventsTab } from "./activity/EventsTab";

interface EventsScreenProps { initialItemId?: number | null; }

export function EventsScreen({ initialItemId = null }: EventsScreenProps) {
  return (
    <div className="era-page era-page-shell">
      {initialItemId === null && <PageHeader title="События" eyebrow="Здесь начинается движение" subtitle="Афиша, программа, регистрация и все детали — без переходов в пустые экраны." />}
      <EventsTab initialItemId={initialItemId} />
    </div>
  );
}
