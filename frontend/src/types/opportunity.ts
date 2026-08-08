export type OpportunityScope = "for_me" | "all" | "saved" | "mine";

export interface Opportunity {
  id: number;
  partner_name: string;
  title: string;
  description: string;
  point_cost: number;
  remaining_slots: string;
  expires_at: string | null;
  instruction: string | null;
  source_url: string | null;
  application_status: string | null;
  is_saved: boolean;
  reasons: string[];
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
