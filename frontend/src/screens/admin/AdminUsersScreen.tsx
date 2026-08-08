import { useState } from "react";
import { PeopleList } from "./people/PeopleList";
import { PersonDetail } from "./people/PersonDetail";

// The Mini App equivalent of the bot's admin:participants / admin:user:*
// flow (app/handlers/admin/rights_block6.py, user_profile_block3_safe.py) —
// search/browse every user (not just pending applications), then manage
// role, block/archive, technical permissions, and direct points/badge
// awards from their card.
export function AdminUsersScreen() {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  if (selectedId === null) {
    return <PeopleList onSelect={setSelectedId} />;
  }
  return <PersonDetail userId={selectedId} onBack={() => setSelectedId(null)} />;
}
