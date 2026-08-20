export type AdminMetricKey =
  | "current_roster"
  | "active_base"
  | "projects_active"
  | "events_live"
  | "event_registrations"
  | "task_results";

export interface AdminMetricRow {
  id: number;
  entity_type: string;
  entity_id: number;
  title: string;
  subtitle: string | null;
  status: string | null;
}

export interface AdminMetricDrilldown {
  metric: AdminMetricKey;
  label: string;
  total: number;
  items: AdminMetricRow[];
}
