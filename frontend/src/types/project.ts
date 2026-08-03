export type ProjectScope = "mine" | "open" | "proposals" | "completed";

export interface ProjectSummary {
  id: number;
  title: string;
  short_description: string;
  status: string;
  author_id: number;
  updated_at: string;
  submitted_at: string | null;
  admin_comment: string | null;
}

export interface ProjectDetail extends ProjectSummary {
  form_data: Record<string, string>;
  can_edit: boolean;
  can_submit: boolean;
  can_delete: boolean;
}

export interface ProjectQuestion {
  key: string;
  block: string;
  title: string;
  prompt: string;
}

export interface ProjectRole {
  id: number;
  title: string;
  description: string | null;
  requirements: string | null;
  capacity: number | null;
  status: string;
  filled: number;
  sort_order: number;
}

export interface ProjectMember {
  id: number;
  user_id: number;
  full_name: string;
  username: string | null;
  role_id: number | null;
  role_title: string | null;
  status: string;
  application_text: string | null;
  joined_at: string | null;
  approved_by: number | null;
  contribution_status: string;
  contribution_summary: string | null;
  contribution_role_title: string | null;
  contribution_result: string | null;
  contribution_confirmed_at: string | null;
  contribution_confirmed_by: number | null;
}

export interface ProjectMilestone {
  id: number;
  title: string;
  description: string | null;
  sort_order: number;
  deadline: string | null;
  responsible_id: number | null;
  status: string;
  completed_at: string | null;
  completed_by: number | null;
}

export interface ProjectTask {
  id: number;
  title: string;
  description: string;
  assignee_id: number | null;
  deadline: string;
  points: number;
  status: string;
  task_type: string;
}

export interface ProjectEvent {
  id: number;
  title: string;
  event_date: string;
  event_time: string;
  status: string;
}

export interface ProjectWorkspace {
  project: ProjectSummary;
  can_manage: boolean;
  viewer_membership_status: string | null;
  progress_percent: number;
  roles: ProjectRole[];
  members: ProjectMember[];
  milestones: ProjectMilestone[];
  tasks: ProjectTask[];
  events: ProjectEvent[];
}

export interface TeamMessageResult {
  total: number;
  sent: number;
  failed: number;
}
