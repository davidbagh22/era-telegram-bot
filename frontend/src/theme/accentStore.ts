import { useEffect, useSyncExternalStore } from "react";
import { fetchUiPreferences, saveUiPreferences } from "../api/client";
import { accentCssVariables, deriveAccent, isValidHex, type ColorScheme } from "./accent";

const STORAGE_KEY = "era.accent.v1";
const PENDING_KEY = "era.accent.pending.v1";
const RESYNC_MIN_INTERVAL_MS = 30_000;

type Listener = () => void;

const listeners = new Set<Listener>();
const appliedProperties = new Set<string>();
let current: string | null = readStored();
let lastSyncAt = 0;
let syncInFlight: Promise<void> | null = null;
let localRevision = 0;
let writeChain: Promise<boolean> = Promise.resolve(true);

function readStored(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isValidHex(raw) ? raw.toLowerCase() : null;
  } catch {
    return null;
  }
}

function writeStored(value: string | null): void {
  try {
    if (value) localStorage.setItem(STORAGE_KEY, value);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode: the server copy is still authoritative */
  }
}

function setPending(pending: boolean): void {
  try {
    if (pending) localStorage.setItem(PENDING_KEY, "1");
    else localStorage.removeItem(PENDING_KEY);
  } catch {
    /* private mode */
  }
}

function isPending(): boolean {
  try {
    return localStorage.getItem(PENDING_KEY) === "1";
  } catch {
    return false;
  }
}

function currentScheme(): ColorScheme {
  // The AURA shell is always dark (see telegram/webApp.ts getColorScheme).
  return "dark";
}

export function applyAccentToDocument(hex: string | null, scheme: ColorScheme = currentScheme()): void {
  const root = document.documentElement;
  for (const name of appliedProperties) root.style.removeProperty(name);
  appliedProperties.clear();
  if (!hex) return;
  const variables = accentCssVariables(deriveAccent(hex, scheme));
  for (const [name, value] of Object.entries(variables)) {
    root.style.setProperty(name, value);
    appliedProperties.add(name);
  }
}

function commit(hex: string | null): void {
  current = hex;
  writeStored(hex);
  applyAccentToDocument(hex);
  listeners.forEach((listener) => listener());
}

/** Apply the cached colour before first paint so the app never flashes the default. */
export function initAccent(): void {
  applyAccentToDocument(current);
}

export function getAccent(): string | null {
  return current;
}

export function subscribeAccent(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function normalizeChoice(hex: string | null): string | null {
  return hex && isValidHex(hex) ? hex.toLowerCase() : null;
}

/** Apply instantly and cache locally; the server copy follows via persistAccent. */
export function setAccentLocal(hex: string | null): void {
  localRevision += 1;
  commit(normalizeChoice(hex));
  setPending(true);
}

/**
 * Writes run one at a time and always send the colour current at the moment they start,
 * so the server ends on the latest choice. Pending is cleared only when no newer local
 * change happened while the request was in flight.
 */
export function persistAccent(): Promise<boolean> {
  const run = writeChain.then(writeLatest);
  writeChain = run;
  return run;
}

async function writeLatest(): Promise<boolean> {
  const revision = localRevision;
  const value = current;
  try {
    await saveUiPreferences(value);
    if (revision === localRevision) setPending(false);
    return true;
  } catch {
    return false;
  }
}

export async function saveAccent(hex: string | null): Promise<boolean> {
  setAccentLocal(hex);
  return persistAccent();
}

async function runSync(): Promise<void> {
  if (isPending()) {
    await persistAccent();
    return;
  }
  const revisionAtRequest = localRevision;
  try {
    const remote = await fetchUiPreferences();
    if (revisionAtRequest !== localRevision || isPending()) return;
    const next = isValidHex(remote.accent_color) ? remote.accent_color.toLowerCase() : null;
    if (next !== current) commit(next);
  } catch {
    /* offline or not yet authorised: keep the cached colour */
  }
}

export function syncAccentFromServer(force = false): Promise<void> {
  if (syncInFlight) return syncInFlight;
  if (!force && Date.now() - lastSyncAt < RESYNC_MIN_INTERVAL_MS) return Promise.resolve();
  lastSyncAt = Date.now();
  syncInFlight = runSync().finally(() => {
    syncInFlight = null;
  });
  return syncInFlight;
}

/** Pull the server preference once authenticated, and again when the app is reopened. */
export function useAccentSync(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return undefined;
    void syncAccentFromServer(true);
    const onVisible = () => {
      if (document.visibilityState === "visible") void syncAccentFromServer();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [enabled]);
}

export function useAccent(): string | null {
  return useSyncExternalStore(subscribeAccent, getAccent, getAccent);
}
