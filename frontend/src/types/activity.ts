export type EventScope = "all" | "for_me" | "mine" | "past";

export interface EventProgramItem {
  title?: string;
  description?: string;
  time?: string;
  responsible?: string;
  notes?: string;
}

export interface EventParticipantTask {
  title?: string;
  description?: string;
  deadline?: string;
  points?: number;
  confirmation_required?: boolean;
  reviewer?: string;
}

export interface EventItem {
  id: number;
  title: string;
  description: string;
  short_description: string | null;
  full_description: string | null;
  event_date: string;
  event_time: string;
  end_time: string | null;
  location: string;
  address: string | null;
  format: string;
  attendance_mode: string;
  category: string | null;
  organizer: string | null;
  participant_value: string | null;
  contact: string | null;
  chat_url: string | null;
  points_for_visit: number;
  project_id: number | null;
  status: string;
  display_status: string;
  participant_limit: number | null;
  registered_count: number;
  available_places: string;
  remaining_count: number | null;
  registration_status: string | null;
  waitlist_enabled: boolean;
  registration_required: boolean;
  registration_close_at: string | null;
  can_register: boolean;
  program: EventProgramItem[];
  participant_tasks: EventParticipantTask[];
  poster_url: string | null;
}

export interface EventActivity {
  id: number;
  title: string;
  description: string;
  submission_type: string;
  points: number;
  my_status: string | null;
  submit_deep_link: string | null;
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
