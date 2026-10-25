export interface LeadershipSystemSnapshot {
  period_start: string;
  period_end: string;
  scope_type: string;
  scope_id: number | null;
  team_size: number;
  tasks_total: number;
  tasks_completed: number;
  tasks_completed_this_week: number;
  tasks_overdue: number;
  tasks_overdue_rate: number;
  projects_active: number;
  events_this_week: number;
  active_goals: number;
}

export interface LeadershipWeeklyReport {
  id: number;
  period_start: string;
  period_end: string;
  scope_type: string;
  scope_id: number | null;
  office_assignment_id: number | null;
  status: "green" | "yellow" | "red";
  main_result: string | null;
  blocker_type: string | null;
  blocker_note: string | null;
  next_priorities: string[];
  needs_help: boolean;
  submitted_at: string | null;
  system_snapshot: LeadershipSystemSnapshot;
  pace_score: number | null;
  clarity_score: number | null;
  load_score: number | null;
  attention_text: string | null;
}

export interface LeadershipWeeklySubmit {
  status: "green" | "yellow" | "red";
  main_result: string;
  blocker_type?: string | null;
  blocker_note?: string;
  next_priorities: string[];
  needs_help: boolean;
  office_assignment_id?: number | null;
  pace_score: number;
  clarity_score: number;
  load_score: number;
  attention_text: string;
}

export interface LeadershipFeedback {
  id: number;
  report_id: number;
  reviewer_id: number;
  status: string;
  comment: string | null;
  created_at: string;
}
