import { apiRequest } from "./client";

export interface ReferralSummary {
  code: string;
  invite_url: string;
  share_text: string;
  registration_points_each: number;
  first_event_points_each: number;
  invited_count: number;
  registered_count: number;
  first_event_count: number;
  earned_points: number;
}

export function fetchReferralSummary(): Promise<ReferralSummary> {
  return apiRequest<ReferralSummary>("/api/v1/referrals/me");
}
