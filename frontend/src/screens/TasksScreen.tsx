import { TasksTab } from "./activity/TasksTab";

interface TasksScreenProps {
  /** A specific task id from `#/tasks/{id}` (deep link, Home's Focus card,
   * a task-squad chat notification, ...). */
  initialItemId?: number | null;
  onBack?: () => void;
}

/**
 * DELTA ToR §7: "Задания" gets its own top-level screen again -- `#/tasks`
 * used to fall through to ActivityScreen's dead landing menu (unreachable
 * from normal navigation, see App.tsx) before landing on TasksTab nested
 * two screens deep. This is the real entry point now; TasksTab itself is
 * unchanged (all 6 scopes + detail view already live there).
 */
export function TasksScreen({ initialItemId = null, onBack }: TasksScreenProps) {
  return (
    <div className="era-page" style={{ padding: "1.25rem 1.25rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        {onBack && (
          <button type="button" onClick={onBack} aria-label="Назад" style={{ minWidth: 44, minHeight: 44, padding: "0.55rem 0.7rem" }}>←</button>
        )}
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>Задания</h1>
      </div>
      <TasksTab initialItemId={initialItemId} />
    </div>
  );
}
