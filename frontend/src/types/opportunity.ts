export type OpportunityScope = "for_me" | "all" | "saved" | "mine";
export type OpportunityDisplayState = "locked" | "almost" | "available" | "new";

export interface EligibilityCheck {
  key: string;
  label: string;
  required: string;
  current: string;
  ok: boolean;
}

export interface Opportunity {
  id: number;
  partner_name: string;
  title: string;
  description: string;
  point_cost: number;
  required_points: number;
  opportunity_type: string;
  min_rank: string | null;
  eligible: boolean;
  display_state: OpportunityDisplayState;
  eligibility_checks: EligibilityCheck[];
  missing_requirements: string[];
  default_award_wording: string | null;
  partner_review_required: boolean;
  remaining_slots: string;
  expires_at: string | null;
  instruction: string | null;
  source_url: string | null;
  application_status: string | null;
  is_saved: boolean;
  reasons: string[];
}
