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
