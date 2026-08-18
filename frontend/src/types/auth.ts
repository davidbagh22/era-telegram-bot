export interface MiniAppUserSummary {
  id: number;
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  role: string;
  application_status: string;
  is_blocked: boolean;
  is_leader: boolean;
  is_admin: boolean;
  permissions: string[];
  onboarding_seen: boolean;
}

export interface MiniAppAuthResponse {
  token: string;
  expires_at: string;
  user: MiniAppUserSummary;
}

export interface ApiErrorBody {
  detail?: string;
}
