export type CareerItemStatus = "self_reported" | "pending" | "verified" | "rejected";
export type CareerPurpose = "work" | "internship" | "university" | "grant" | "volunteer" | "universal";

export interface CareerLanguage {
  name: string;
  level: string;
}

export interface CareerProfileData {
  headline: string;
  about: string;
  languages: CareerLanguage[];
}

export interface CareerPortfolioItem {
  id: number;
  item_type: string;
  title: string;
  organization: string;
  description: string;
  issued_at: string | null;
  url: string | null;
  file_name: string | null;
  has_file: boolean;
  status: CareerItemStatus;
  include_in_resume: boolean;
  admin_comment: string | null;
}

export interface CareerRecommendationFacts {
  attended_events: number;
  completed_tasks: number;
  authored_projects: number;
  confirmed_project_contributions: number;
  leadership_roles: string[];
  verified_external_items: number;
}

export interface AutomaticCareerRecommendation {
  text: string;
  facts: CareerRecommendationFacts;
  privacy_note: string;
}

export interface OfficialRecommendation {
  id: number;
  purpose: CareerPurpose;
  status: "requested" | "approved" | "rejected";
  draft_text: string;
  final_text: string | null;
  document_number: string | null;
  requested_at: string;
  approved_at: string | null;
  rejection_comment: string | null;
  can_download: boolean;
}

export interface CareerDashboard {
  profile: CareerProfileData;
  counts: {
    confirmed: number;
    added_by_me: number;
    pending: number;
    evidence_files: number;
  };
  items: CareerPortfolioItem[];
  automatic_recommendation: AutomaticCareerRecommendation;
  official_recommendation: OfficialRecommendation | null;
}

export interface CareerItemPayload {
  item_type: string;
  title: string;
  organization?: string;
  description?: string;
  issued_at?: string | null;
  url?: string;
  include_in_resume?: boolean;
}

export interface AdminCareerItem extends CareerPortfolioItem {
  user_id: number;
  user_name: string;
}

export interface AdminRecommendation extends OfficialRecommendation {
  user_id: number;
  user_name: string;
}
