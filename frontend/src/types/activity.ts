export type EventScope = "all" | "for_me" | "mine" | "past";

export interface EventItem {
  id: number;
  title: string;
  description: string;
  event_date: string;
  event_time: string;
  location: string;
  format: string;
  points_for_visit: number;
  project_id: number | null;
  available_places: string;
  registration_status: string | null;
}

export type TaskScope = "available" | "mine" | "review" | "completed";

export interface TaskItem {
  id: number;
  title: string;
  description: string;
  deadline: string;
  points: number;
  status: string;
  task_type: string;
  is_joined_or_assigned: boolean;
  can_submit: boolean;
  submit_deep_link: string | null;
}

export interface CalendarItem {
  kind: "event" | "task";
  id: number;
  title: string;
  date: string;
  time: string | null;
}

export interface HistoryEntry {
  kind: "event_attended" | "task_completed" | "portfolio" | "points";
  title: string;
  date: string;
  detail: string;
}
