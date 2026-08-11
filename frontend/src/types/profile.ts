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

// Self-service data rights — see app/services/data_rights_service.py.
export interface DeletionRequest {
  id: number;
  status: "pending" | "fulfilled" | "rejected";
  created_at: string;
}

// Admin's view of the same request, with just enough of the target user's
// identity to review it — see app/api/v1/admin.py's DeletionRequestOut.
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
