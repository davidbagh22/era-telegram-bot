import { ApiError, authenticate } from "./client";

export interface SystemCheck {
  key: string;
  title: string;
  status: string;
  severity: string;
  detail: string;
}

export interface DiagnosticRun {
  id: number;
  run_type: string;
  status: string;
  score: number;
  checks: SystemCheck[];
  commit_sha: string | null;
  duration_ms: number | null;
  created_at?: string | null;
}

export interface SystemIncident {
  id: number;
  severity: string;
  status: string;
  title: string;
  detail: string;
  check_key: string | null;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  current_commit: string | null;
  last_healthy_commit: string | null;
  fix_prompt: string | null;
}

export interface BackupHistoryItem {
  id: number;
  backup_key: string;
  backup_type: string;
  status: string;
  storage_provider: string;
  storage_reference: string | null;
  checksum_sha256: string | null;
  size_bytes: number | null;
  completed_at: string | null;
  restore_verified_at: string | null;
  error_code: string | null;
  error_detail: string | null;
  created_at: string | null;
}

export interface SystemSnapshot {
  latest: DiagnosticRun | null;
  latest_full: DiagnosticRun | null;
  incidents: SystemIncident[];
  backups: BackupHistoryItem[];
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

function devTelegramId(): number | undefined {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function systemToken(): Promise<string> {
  if (!tokenPromise) {
    const initData = window.Telegram?.WebApp?.initData ?? "";
    tokenPromise = authenticate(initData, devTelegramId()).then((result) => result.token);
  }
  try {
    return await tokenPromise;
  } catch (error) {
    tokenPromise = null;
    throw error;
  }
}

async function systemRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await systemToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep status text when the response is not JSON.
    }
    if (response.status === 401) tokenPromise = null;
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function fetchSystemSnapshot(): Promise<SystemSnapshot> {
  return systemRequest<SystemSnapshot>("/api/v1/admin/system");
}

export function runSystemDiagnostic(runType: "heartbeat" | "full" = "full"): Promise<DiagnosticRun> {
  return systemRequest<DiagnosticRun>("/api/v1/admin/system/diagnostics", {
    method: "POST",
    body: JSON.stringify({ run_type: runType }),
  });
}
