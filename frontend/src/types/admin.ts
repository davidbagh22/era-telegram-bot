export interface DashboardData {
  metrics: Record<string, number>;
  attention_total: number;
}

export interface PendingApplication {
  id: number;
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  city: string | null;
  occupation: string | null;
  motivation: string | null;
  application_status: string;
  created_at: string;
}

export type ProjectDecisionAction =
  | "initial_accept"
  | "venue_approve"
  | "revise"
  | "postpone"
  | "reject";

export interface ProjectForModeration {
  id: number;
  title: string;
  short_description: string;
  status: string;
  author_id: number;
  submitted_at: string | null;
  admin_comment: string | null;
}
