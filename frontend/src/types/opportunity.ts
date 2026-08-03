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
