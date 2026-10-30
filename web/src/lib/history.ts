import type { Intent, SourcePayload } from "@/lib/types";

export const HISTORY_KEY = "lawqa.history.v1";
export const MAX_HISTORY = 30;

export interface HistoryEntry {
  id: string;
  question: string;
  answer: string;
  intent: Intent | null;
  sources: SourcePayload[];
  missingFacts: string[];
  disclaimer: string;
  askedAt: string;
}

const EMPTY: HistoryEntry[] = [];
let entries: HistoryEntry[] | null = null;
const listeners = new Set<() => void>();

/** Storage can throw (private mode, blocked site data); history then lives in memory only. */
function read(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function write(next: HistoryEntry[]): void {
  entries = next;
  try {
    if (next.length) localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
    else localStorage.removeItem(HISTORY_KEY);
  } catch {
    // keep the in-memory copy
  }
  listeners.forEach((listener) => listener());
}

export function getHistory(): HistoryEntry[] {
  if (typeof window === "undefined") return EMPTY;
  entries ??= read();
  return entries;
}

export function getServerHistory(): HistoryEntry[] {
  return EMPTY;
}

export function subscribeHistory(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function addEntry(entry: HistoryEntry): void {
  const rest = getHistory().filter((e) => e.question !== entry.question);
  write([entry, ...rest].slice(0, MAX_HISTORY));
}

export function clearHistory(): void {
  write([]);
}
