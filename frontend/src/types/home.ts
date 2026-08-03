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

export interface HomeSnapshot {
  growth: GrowthProgress;
  points_balance: number;
  next_step: NextStep | null;
  nearest_event: EventSummary | null;
  active_task: TaskSummary | null;
  active_project: ProjectSummary | null;
  opportunities: OpportunitySummary[];
}
