export interface DashboardData {
  metrics: Record<string, number>;
  attention_total: number;
}

// Admin Mode Overview's "Последняя активность" — see
// app/services/admin_activity_feed_service.py.
export interface ActivityFeedEntry {
  id: number;
  actor_name: string | null;
  summary: string;
  entity_type: string;
  created_at: string;
}

// Mini App equivalent of the bot's "📊 Аналитика и Excel" flow — see
// app/services/admin_analytics_service.py.
export interface AnalyticsSummary {
  total_users: number;
  approved_users: number;
  pending_users: number;
  events: number;
  projects: number;
  contacts: number;
  goals: number;
}

export type AnalyticsExcelSection = "all" | "users" | "departments" | "events" | "projects";

export interface PendingApplication {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string;
  last_name: string | null;
  birth_date: string | null;
  age: number | null;
  phone: string | null;
  email: string | null;
  city: string | null;
  education_work: string | null;
  occupation: string | null;
  skills: string[];
  experience: string | null;
  motivation: string | null;
  available_time: string | null;
  desired_path: string | null;
  departments: string[];
  directions: string[];
  social_links: SocialLinkItem[];
  personal_data_consent: boolean;
  consent_policy_version: string | null;
  application_status: string;
  photo_attached: boolean;
  photo_data_url: string | null;
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

export interface SurveyAdmin {
  id: number;
  title: string;
  description: string | null;
  questions: string[];
  status: string;
  is_monthly: boolean;
  sent_at: string | null;
  response_count: number;
}

export interface SurveyResponseAdmin {
  user_id: number;
  user_name: string;
  submitted_at: string | null;
  answers: { question: string; answer: string }[];
}

export interface RewardAdmin {
  id: number;
  name: string;
  description: string;
  point_cost: number;
  quantity: number | null;
  is_active: boolean;
}

export interface EventActivityAdmin {
  id: number;
  title: string;
  description: string;
  submission_type: string;
  points: number;
  is_active: boolean;
}

export interface ActivitySubmissionAdmin {
  id: number;
  activity_id: number;
  activity_title: string;
  points: number;
  event_title: string;
  user_id: number;
  user_name: string;
  status: string;
  text: string | null;
  file_type: string | null;
}

export interface RedemptionAdmin {
  id: number;
  reward_id: number;
  reward_name: string;
  user_id: number;
  user_name: string;
  points_spent: number;
  status: string;
  admin_comment: string | null;
}

// Mini App equivalents of the bot's "🎯 Ежемесячные цели", "🤝 База
// организаций", "🏛 Редактор структуры" and "👋 Автоматические приветствия"
// flows — see app/services/admin_goals_service.py, admin_contacts_service.py,
// admin_structure_service.py, admin_greetings_service.py.
export interface GoalItem {
  id: number;
  month: string;
  title: string;
  target_value: number;
  current_value: number;
  status: string;
  scope_type: string;
  scope_name: string | null;
}

export interface GoalCreatePayload {
  title: string;
  target_value: number;
  month?: string | null;
  scope_query?: string | null;
}

export type GoalDecisionAction = "inc" | "done" | "delete";

export interface OrganizationContactItem {
  id: number;
  organization_name: string;
  contact_name: string | null;
  position: string | null;
  second_contact_name: string | null;
  second_position: string | null;
  email: string | null;
  phone: string | null;
  notes: string | null;
}

export interface OrganizationContactCreatePayload {
  organization_name: string;
  contact_name?: string | null;
  position?: string | null;
  second_contact_name?: string | null;
  second_position?: string | null;
  email?: string | null;
  phone?: string | null;
  notes?: string | null;
}

export interface DepartmentStructureItem {
  id: number;
  name: string;
  description: string | null;
}

// chat_key is one of "general" | "internal" | "external" | "leaders" — see
// app/services/chat_access_service.py's CHAT_SETTING_KEYS.
export interface ChatGreetingItem {
  id: number;
  chat_key: string;
  title: string;
  text: string;
  is_enabled: boolean;
  is_bound: boolean;
}

// Chat Infrastructure Registry — one row per org chat, combining binding
// (app/services/chat_access_service.py), the greeting toggle above, and
// recent send/error history from the audit log. See
// app/services/chat_registry_service.py.
export interface ChatRegistryItem {
  chat_key: string;
  title: string;
  chat_id: number | null;
  is_bound: boolean;
  permission_description: string;
  greeting_enabled: boolean | null;
  last_sent_at: string | null;
  last_error_at: string | null;
}

export interface ChatHealthResult {
  chat_key: string;
  ok: boolean;
  detail: string;
}

// Mini App equivalent of the bot's "📨 Рассылка в личные сообщения" and
// "📣 Сообщение в выбранные чаты" flows — see app/services/admin_broadcast_service.py.
export type BroadcastAudience = "all" | "role" | "department" | "direction" | "age" | "city";

export interface AudienceOption {
  value: string;
  label: string;
}

export interface BroadcastAudienceOptions {
  roles: AudienceOption[];
  departments: AudienceOption[];
  directions: AudienceOption[];
  ages: AudienceOption[];
}

export interface PersonalBroadcastPayload {
  audience: BroadcastAudience;
  filter_value?: string | null;
  text: string;
}

export interface BroadcastPreviewCount {
  count: number;
}

export interface PersonalBroadcastResult {
  total: number;
  sent: number;
  failed: number;
  duplicates: number;
  temporary_failed: number;
  permanent_failed: number;
}

export type ChatBroadcastKey = "general" | "internal" | "external" | "leaders";

// Mini App equivalent of the bot's "🧹 Очистка тестовых данных" flow — see
// app/services/maintenance_service.py. Destructive and irreversible: the
// server re-validates confirmation_phrase itself, this isn't a UI-only gate.
export interface MaintenancePreview {
  counts: Record<string, number>;
  total: number;
  confirmation_phrase: string;
}

export interface MaintenanceResetResult {
  counts: Record<string, number>;
  total: number;
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
