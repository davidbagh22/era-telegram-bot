export type OpportunityScope = "for_me" | "all" | "saved" | "mine";
export type OpportunityState = "available" | "almost" | "closed" | "requested" | "review" | "issued";
export type OpportunitySort = "closing_soon" | "newest" | "by_organization";

export interface EligibilityCheck {
  key: string;
  label: string;
  required: string;
  current: string;
  ok: boolean;
}

export interface OpportunityFacets {
  issuers: string[];
  types: string[];
  categories: string[];
}

export interface Opportunity {
  id: number;
  partner_name: string;
  title: string;
  description: string;
  /** Legacy external offers may still use this as a redeemable cost. For
   * recognition opportunities use required_points and never subtract it. */
  point_cost: number;
  required_points: number;
  opportunity_type: "external" | "certificate" | "letter" | string;
  category: string | null;
  min_rank: string | null;
  eligible: boolean;
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
  is_offer_open: boolean;
  state: OpportunityState;
}

export interface Auction {
  id: number;
  title: string;
  description: string;
  top_bid: number | null;
  top_bidder: string | null;
  my_bid: number | null;
  next_minimum_bid: number;
  bid_step: number;
  ends_at: string;
  is_open: boolean;
}

export interface Survey {
  id: number;
  title: string;
  description: string | null;
  questions: string[];
  completed: boolean;
}

export interface SurveyDetail extends Survey {
  answers: string[] | null;
}

export interface Reward {
  id: number;
  name: string;
  description: string;
  point_cost: number;
  quantity: number | null;
  my_status: string | null;
}
