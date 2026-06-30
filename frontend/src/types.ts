export interface UserStats {
  points: number;
  events: number;
  projects: number;
  completed_projects: number;
  tasks: number;
  portfolio: number;
}

export interface EraUser {
  id: number;
  telegram_id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  age?: number;
  city?: string;
  education_work?: string;
  occupation?: string;
  skills: string[];
  role: string;
  role_label: string;
  participation_status: string;
  status_label: string;
  application_status: string;
  departments: string[];
  directions: string[];
  is_privileged: boolean;
  is_admin: boolean;
  stats: UserStats;
}

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
}

export interface SessionResponse {
  state: "needs_registration" | "pending" | "rejected" | "needs_info" | "ready";
  telegram_user: TelegramUser;
  user: EraUser | null;
}

export interface DashboardData {
  user: EraUser;
  rating_place: number | null;
  upcoming_events: Array<{
    id: number;
    title: string;
    date: string;
    time: string;
    location: string;
    points: number;
  }>;
  active_tasks: Array<{
    id: number;
    title: string;
    deadline: string;
    status: string;
    points: number;
  }>;
}

export interface EventItem {
  id: number;
  title: string;
  description: string;
  date: string;
  time: string;
  location: string;
  format: string;
  points: number;
  available_places: string;
  registration_status?: string;
}

export interface ProjectItem {
  id: number;
  title: string;
  description: string;
  status: string;
  document?: string;
  created_at: string;
}

export interface PortfolioItem {
  id: number;
  title: string;
  type: string;
  description?: string;
  url?: string;
  issued_at?: string;
}

export interface TaskItem {
  id: number;
  title: string;
  description: string;
  deadline: string;
  status: string;
  points: number;
}

export interface RatingItem {
  place: number;
  name: string;
  points: number;
  is_current_user: boolean;
}
