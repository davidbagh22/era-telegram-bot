import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";
import type { OfferAdmin, Partner } from "../types/admin";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

function devTelegramId(): number | undefined {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function token(): Promise<string> {
  if (!tokenPromise) {
    tokenPromise = authenticate(getInitData(), devTelegramId())
      .then((result) => result.token)
      .catch((error) => {
        tokenPromise = null;
        throw error;
      });
  }
  return tokenPromise;
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${await token()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = response.statusText || "request_failed";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // No response body is surfaced to the UI.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function updatePartner(
  partnerId: number,
  payload: { name?: string; description?: string; source_url?: string | null },
): Promise<Partner> {
  return patch<Partner>(`/api/v1/admin/partners/${partnerId}`, payload);
}

export function updateOffer(
  offerId: number,
  payload: {
    partner_id?: number;
    title?: string;
    description?: string;
    point_cost?: number;
    quantity?: number | null;
    instruction?: string | null;
    source_url?: string | null;
    expires_at?: string | null;
  },
): Promise<OfferAdmin> {
  return patch<OfferAdmin>(`/api/v1/admin/offers/${offerId}`, payload);
}
