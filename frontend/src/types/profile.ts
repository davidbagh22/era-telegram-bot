export interface GrowthProgress {
  level: string;
  label: string;
  level_index: number;
  level_count: number;
}

export interface PortfolioEntry {
  title: string;
  description: string;
  status: string;
  date_label: string;
  category: string;
  file_id: string | null;
  url: string | null;
  entity_kind: "project" | "event" | "task" | null;
  entity_id: number | null;
}

export interface Profile {
  id: number;
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  role: string;
  growth: GrowthProgress;
  full_name: string;
  participation_status: string;
  departments: string[];
  directions: string[];
  period: string;
  city: string;
  email: string;
  education_work: string;
  occupation: string;
  experience: string;
  motivation: string;
  skills: string[];
  stats: Record<string, number>;
  projects: PortfolioEntry[];
  events: PortfolioEntry[];
  tasks: PortfolioEntry[];
  volunteer: PortfolioEntry[];
  leadership: PortfolioEntry[];
  badges: PortfolioEntry[];
  certificates: PortfolioEntry[];
  recommendations: PortfolioEntry[];
}

export interface DeletionRequest {
  id: number;
  status: "pending" | "fulfilled" | "rejected";
  created_at: string;
}

export interface AdminDeletionRequest {
  id: number;
  user_id: number;
  first_name: string;
  last_name: string | null;
  telegram_id: number;
  note: string | null;
  status: "pending" | "fulfilled" | "rejected";
  created_at: string;
}
