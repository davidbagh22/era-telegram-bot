export interface LeaderboardEntry {
  rank: number;
  display_name: string;
  points: number;
  growth_level: string;
  is_you: boolean;
}

export interface Leaderboard {
  entries: LeaderboardEntry[];
  me: LeaderboardEntry | null;
}
