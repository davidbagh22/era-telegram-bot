export type VectorDimension = "energy" | "agency" | "autonomy" | "connection" | "direction";

export interface VectorQuestion { code: string; title: string; text: string; theme?: string; }
export interface VectorOption { value: number; label: string; }
export interface VectorInsight {
  title?: string;
  support?: string;
  tension?: string;
  change?: string;
  insight?: string;
  why?: string;
  focus?: string;
  experiment?: string;
  semantic_tag?: string;
  methodology_version?: string;
  theme?: string | null;
  disclaimer?: string;
}
export interface VectorCheckin {
  id: number;
  month: string;
  theme?: string | null;
  status: "in_progress" | "completed";
  answers: Record<string, number>;
  state: Partial<Record<VectorDimension, number>>;
  index: number | null;
  delta: Partial<Record<VectorDimension, number>>;
  insight: VectorInsight;
  completed_at: string | null;
  context: { factors: string[]; development_wants: string[] };
}
export interface VectorProfile { index: number | null; state: Partial<Record<VectorDimension, number>>; baseline: Partial<Record<VectorDimension, number>>; last_checkin_at: string | null; notice: string; }
export interface DevelopmentGoal { id: number; month: string; title: string; experiment: string | null; semantic_tag: string | null; status: string; is_custom: boolean; review: { result: string; obstacle: string | null; note: string | null } | null; }
export interface DevelopmentHome { title: string; subtitle: string; consent_required: boolean; consent_version: string; profile: VectorProfile | null; current_checkin: VectorCheckin | null; current_goal: DevelopmentGoal | null; questions: VectorQuestion[]; answer_options: VectorOption[]; context_options: string[]; development_wants: string[]; state_labels: Record<VectorDimension, string>; }

export interface AssessmentScore { raw: number; normalized: number; }
export interface AssessmentResult { session_id: number; assessment_code: string; title: string; version: string; completed_at: string | null; scores: Record<string, AssessmentScore>; interpretation: { title: string; summary: string; note: string } | null; notice?: string | null; }
export interface AssessmentCard { code: string; title: string; description: string | null; source: string; methodology: string; license: string | null; license_status: string; estimated_minutes: number; min_age: number | null; recommended_retake_after_days: number | null; construct_type: string; available: boolean; version?: string | null; language?: string; translation_source?: string | null; notice?: string | null; validation_note?: string | null; question_count?: number; what_it_shows?: string | null; important?: string; last_result?: AssessmentResult | null; strengths?: string[]; interest_code?: string[]; }
export interface AssessmentQuestionOption { value: number; label: string; }
export interface AssessmentQuestion { code: string; text: string; position: number; scale_code: string | null; options: AssessmentQuestionOption[]; }
export interface AssessmentSession { id: number; assessment_code: string; title: string; version: string; status: "in_progress" | "completed"; started_at: string | null; completed_at: string | null; questions: AssessmentQuestion[]; answers: Record<string, number>; answered_count: number; question_count: number; notice?: string | null; }

export interface DevelopmentPrivacy { consent_version: string; admin_visibility: { summary: boolean; interests: boolean; goals: boolean }; admin_can_see: string[]; private_only: string[]; }
export interface RememberedNote { id: number; text: string; created_at: string; checkin_id: number | null; }
export interface PersonalInsightItem { id: number; text: string; semantic_tag: string | null; accepted: boolean | null; created_at: string; }

export interface DevelopmentAnalytics {
  sample_size: number;
  eligible_profiles: number;
  coverage_percent: number;
  minimum_cohort: number;
  suppressed: boolean;
  state: Partial<Record<VectorDimension, number>> | null;
  index?: number | null;
  disclaimer?: string;
  message?: string;
  delta?: Partial<Record<VectorDimension, number>>;
  development_wants?: Array<{ key: string; count: number; percent: number }>;
  interests?: Array<{ key: string; count: number; percent: number }>;
  recommendation?: string | null;
}

export interface AdminDevelopmentProfile {
  user: { id: number; first_name: string; last_name: string | null };
  last_checkin_at: string | null;
  state: Partial<Record<VectorDimension, number>>;
  index: number | null;
  baseline: Partial<Record<VectorDimension, number>>;
  traits: Record<string, unknown>;
  needs: Record<string, unknown>;
  interests: Record<string, unknown> | null;
  strengths: string[] | null;
  environment: Record<string, unknown> | null;
  current_focus: { title: string; experiment: string | null; status: string; review_result: string | null } | null;
  history: Array<{ month: string; index: number | null; state: Partial<Record<VectorDimension, number>>; delta: Partial<Record<VectorDimension, number>> }>;
  notice: string;
  never_exposed_here: string[];
}
