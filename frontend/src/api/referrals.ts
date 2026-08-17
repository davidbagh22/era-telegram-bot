import { authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

export interface ReferralSummary {
  code: string;
  invite_url: string;
  share_text: string;
  registration_points_each: number;
  first_event_points_each: number;
  active_points_each: number;
  per_invitee_cap: number;
  monthly_cap: number;
  invited_count: number;
  registered_count: number;
  first_event_count: number;
  active_count: number;
  earned_points: number;
  monthly_earned_points: number;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let referralToken: string | null = null;

async function token(): Promise<string> {
  if (referralToken) return referralToken;
  const parameter = new URLSearchParams(window.location.search).get("devTelegramId");
  const id = parameter ? Number(parameter) : undefined;
  const auth = await authenticate(getInitData(), id);
  referralToken = auth.token;
  return referralToken;
}

export async function fetchReferralSummary(retry = true): Promise<ReferralSummary> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/referrals/me`, {
    headers: { Authorization: `Bearer ${bearer}` },
  });
  if (response.status === 401 && retry) {
    referralToken = null;
    return fetchReferralSummary(false);
  }
  if (!response.ok) {
    throw new Error(`referral_summary_${response.status}`);
  }
  return (await response.json()) as ReferralSummary;
}
