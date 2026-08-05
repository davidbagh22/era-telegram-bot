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

export type EventDecisionAction = "approve" | "revise" | "reject";

export interface EventForModeration {
  id: number;
  title: string;
  description: string;
  event_date: string;
  event_time: string;
  location: string;
  status: string;
}

export type TaskReviewAction = "approve" | "revision" | "reject";

export interface TaskSubmissionForReview {
  id: number;
  task_id: number;
  task_title: string;
  points: number;
  participant_id: number;
  participant_name: string;
  text: string | null;
  file_id: string | null;
  status: string;
  admin_comment: string | null;
}

export type OfferApplicationAction = "approve" | "reject";

export interface OfferApplicationForReview {
  id: number;
  offer_id: number;
  offer_title: string;
  point_cost: number;
  participant_id: number;
  participant_name: string;
  participant_balance: number;
  status: string;
}
