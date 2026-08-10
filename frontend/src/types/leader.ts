export interface LeaderParticipant {
  id: number;
  first_name: string;
  last_name: string | null;
  participation_status: string;
}

export interface LeaderEvent {
  id: number;
  title: string;
  status: string;
  event_date: string;
  event_time: string;
}

export interface LeaderProject {
  id: number;
  title: string;
  status: string;
}

export interface LeaderTask {
  id: number;
  title: string;
  status: string;
  deadline: string;
  points: number;
  assignee_id: number | null;
}

export interface LeaderOverview {
  departments: string[];
  directions: string[];
  participants: LeaderParticipant[];
  events: LeaderEvent[];
  projects: LeaderProject[];
  tasks: LeaderTask[];
}

export interface LeaderApplication {
  user_id: number;
  first_name: string;
  last_name: string | null;
  username: string | null;
  status: string;
}

export interface LeaderOpenTask {
  id: number;
  title: string;
  description: string;
  deadline: string;
  points: number;
  max_participants: number | null;
  applications: LeaderApplication[];
}

export interface OpenTaskCreatePayload {
  title: string;
  description: string;
  deadline: string;
  points: number;
  max_participants: number;
}

export interface ActivitySubmission {
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
