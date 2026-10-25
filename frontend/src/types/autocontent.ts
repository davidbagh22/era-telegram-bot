export type AutoContentType =
  | "morning_quote"
  | "evening_quote"
  | "weekly_challenge"
  | "monthly_theme"
  | "holiday";

export type AutoContentSlot = "morning" | "evening";

export interface AutoContentSettings {
  paused: boolean;
  quotes: boolean;
  challenges: boolean;
  themes: boolean;
  holidays: boolean;
}

export interface AutoContentPlannedItem {
  content_id: string;
  content_type: AutoContentType;
  slot: AutoContentSlot;
  text: string;
  title: string | null;
  date_key: string | null;
  source: "pack" | "custom" | string;
  planned_at: string;
  effective_text: string;
}

export interface AutoContentCalendarEntry {
  date: string;
  slot: AutoContentSlot;
  planned: AutoContentPlannedItem | null;
  status: string;
  delivery_id: number | null;
  message_id: number | null;
  error_code: string | null;
}

export interface AutoContentCustomHoliday {
  content_id: string;
  date_key: string;
  title: string | null;
  text: string;
  is_enabled: boolean;
  is_skipped: boolean;
}

export interface AutoContentOverview {
  settings: AutoContentSettings;
  items: AutoContentCalendarEntry[];
  custom_holidays: AutoContentCustomHoliday[];
  timezone: string;
}

export interface AutoContentHistoryEntry {
  id: number;
  content_id: string;
  content_type: AutoContentType;
  slot: AutoContentSlot;
  status: string;
  planned_at: string;
  sent_at: string | null;
  attempts: number;
  error_code: string | null;
  is_manual: boolean;
}

export interface AutoContentItemPatch {
  text?: string;
  is_enabled?: boolean;
  is_skipped?: boolean;
  title?: string;
}

export interface AutoContentPreview {
  text: string;
  characters: number;
  lines: number;
  parse_mode: "HTML";
}
