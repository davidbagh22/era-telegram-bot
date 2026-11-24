export interface LiteratureCatalog {
  latest: number; subscribed: boolean;
  items: { number: number; title: string }[];
}
export interface LiteratureIssue {
  number: number; title: string; summary: string; example: string;
  critical_view: string; reflection_question: string; practical_task: string;
}
export interface GamesCatalog {
  enabled: boolean; launch_url: string | null;
  items: { id: string; title: string; players: string; minutes: string; rules: string; group: boolean }[];
}
