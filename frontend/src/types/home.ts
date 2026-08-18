export interface GrowthProgress {
  level: "participant" | "active" | "leader";
  label: string;
  level_index: number;
  level_count: number;
}

export interface NextStep {
  kind: "task" | "event" | "project" | "growth" | "opportunity";
  title: string;
  description: string;
  entity_id: number | null;
  route: string | null;
  action_label: string;
}

export interface EventSummary {
  id: number;
  title: string;
  event_date: string;
  event_time: string;
  location: string;
}

export interface TaskSummary {
  id: number;
  title: string;
  deadline: string;
  points: number;
  status: string;
}

export interface ProjectSummary {
  id: number;
  title: string;
  status: string;
}

export interface OpportunitySummary {
  id: number;
  title: string;
  point_cost: number;
  expires_at: string | null;
}

export interface RankProgress {
  rank: string;
  rank_label: string;
  next_rank_label: string | null;
}

export interface OpportunityProgress {
  id: number;
  title: string;
  issuer: string;
  points_needed: number;
}

export interface ActivityStats {
  points: number;
  projects: number;
  completed_tasks: number;
  portfolio_items: number;
}

export interface HomeSnapshot {
  growth: GrowthProgress;
  rank: RankProgress;
  points_balance: number;
  activity: ActivityStats;
  next_step: NextStep | null;
  nearest_event: EventSummary | null;
  active_task: TaskSummary | null;
  active_project: ProjectSummary | null;
  opportunities: OpportunitySummary[];
  new_opportunity: OpportunityProgress | null;
  nearest_locked_opportunity: OpportunityProgress | null;
  tasks_available_count: number;
  tasks_in_progress_count: number;
}
