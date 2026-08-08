export interface DashboardData {
  metrics: Record<string, number>;
  attention_total: number;
}

export interface PendingApplication {
  id: number;
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  city: string | null;
  occupation: string | null;
  motivation: string | null;
  application_status: string;
  created_at: string;
}

export type ProjectDecisionAction =
  | "initial_accept"
  | "venue_approve"
  | "revise"
  | "postpone"
  | "reject";

export interface ProjectForModeration {
  id: number;
  title: string;
  short_description: string;
  status: string;
  author_id: number;
  submitted_at: string | null;
  admin_comment: string | null;
}

export type EventDecisionAction = "approve" | "revise" | "reject";

export interface EventForModeration {
  id: number;
  title: string;
  description: string;
  event_date: string;
  event_time: string;
  location: string;
  status: string;
}

export type TaskReviewAction = "approve" | "revision" | "reject";

export interface TaskSubmissionForReview {
  id: number;
  task_id: number;
  task_title: string;
  points: number;
  participant_id: number;
  participant_name: string;
  text: string | null;
  file_id: string | null;
  status: string;
  admin_comment: string | null;
}

export type OfferApplicationAction = "approve" | "reject";

export interface OfferApplicationForReview {
  id: number;
  offer_id: number;
  offer_title: string;
  point_cost: number;
  participant_id: number;
  participant_name: string;
  participant_balance: number;
  status: string;
}

export interface UserListItem {
  id: number;
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  username: string | null;
  role: string;
  application_status: string;
  is_blocked: boolean;
  is_archived: boolean;
}

export interface UserListResult {
  items: UserListItem[];
  total: number;
}

export interface BadgeItem {
  id: number;
  name: string;
}

export interface SocialLinkItem {
  platform: string;
  url: string;
}

export interface TeamPost {
  project_id: number;
  project_title: string;
  author_name: string;
  text: string;
  status: string;
}

export interface OperationalEvent {
  id: number;
  title: string;
  event_date: string;
  event_time: string;
  location: string;
  status: string;
  points_for_visit: number;
  registered: number;
  free: number | string;
}

export interface EventParticipant {
  registration_id: number;
  participant_id: number;
  participant_name: string;
  status: string;
}

export interface Partner {
  id: number;
  name: string;
  description: string;
  source_url: string | null;
  is_active: boolean;
  is_archived: boolean;
}

export interface OfferAdmin {
  id: number;
  partner_id: number;
  partner_name: string;
  title: string;
  description: string;
  point_cost: number;
  quantity: number | null;
  expires_at: string | null;
  instruction: string | null;
  source_url: string | null;
  is_active: boolean;
  is_archived: boolean;
}

export interface OfficeAssignment {
  assignment_id: number;
  user_id: number;
  user_name: string;
}

export interface Office {
  id: number;
  title: string;
  description: string | null;
  is_active: boolean;
  assignments: OfficeAssignment[];
}

export interface AuctionBid {
  bid_id: number;
  bidder_id: number;
  bidder_name: string;
  amount: number;
}

export interface AuctionAdmin {
  id: number;
  title: string;
  description: string;
  status: string;
  minimum_bid: number;
  bid_step: number;
  ends_at: string;
  top_bid: number | null;
  bids: AuctionBid[];
}

export interface UserDetail {
  id: number;
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  username: string | null;
  role: string;
  application_status: string;
  participation_status: string;
  is_blocked: boolean;
  is_archived: boolean;
  city: string | null;
  phone: string | null;
  email: string | null;
  occupation: string | null;
  motivation: string | null;
  points_balance: number;
  portfolio_count: number;
  badges: BadgeItem[];
  available_badges: BadgeItem[];
  permissions: Record<string, boolean>;
  social_links: SocialLinkItem[];
  can_manage: boolean;
  can_manage_permissions: boolean;
  can_award_points: boolean;
}
