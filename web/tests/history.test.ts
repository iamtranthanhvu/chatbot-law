import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  HISTORY_KEY,
  MAX_HISTORY,
  addEntry,
  clearHistory,
  getHistory,
  type HistoryEntry,
} from "@/lib/history";

function entry(id: string, question = `câu ${id}`): HistoryEntry {
  return {
    id,
    question,
    answer: "Trả lời [1].",
    intent: "lookup",
    sources: [],
    missingFacts: [],
    disclaimer: "Tham khảo.",
    askedAt: "2026-10-30T10:00:00.000Z",
  };
}

beforeEach(() => {
  localStorage.clear();
  clearHistory();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("history", () => {
  it("keeps the newest question first and survives a reload of the store", () => {
    addEntry(entry("a"));
    addEntry(entry("b"));

    expect(getHistory().map((e) => e.id)).toEqual(["b", "a"]);
    expect(JSON.parse(localStorage.getItem(HISTORY_KEY)!).map((e: HistoryEntry) => e.id)).toEqual([
      "b",
      "a",
    ]);
  });

  it("keeps a bounded number of entries", () => {
    for (let i = 0; i < MAX_HISTORY + 5; i++) addEntry(entry(String(i)));

    expect(getHistory()).toHaveLength(MAX_HISTORY);
    expect(getHistory()[0].id).toBe(String(MAX_HISTORY + 4));
  });

  it("asking the same question again moves it to the top instead of duplicating it", () => {
    addEntry(entry("a", "Điều 100?"));
    addEntry(entry("b", "khác"));
    addEntry(entry("c", "Điều 100?"));

    expect(getHistory().map((e) => e.id)).toEqual(["c", "b"]);
  });

  it("can be cleared", () => {
    addEntry(entry("a"));

    clearHistory();

    expect(getHistory()).toEqual([]);
    expect(localStorage.getItem(HISTORY_KEY)).toBeNull();
  });

  it("works in memory when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(() => addEntry(entry("a"))).not.toThrow();
    expect(getHistory().map((e) => e.id)).toEqual(["a"]);
  });

  it("ignores corrupt stored data", async () => {
    localStorage.setItem(HISTORY_KEY, "{không phải json");
    vi.resetModules();
    const fresh = await import("@/lib/history");

    expect(fresh.getHistory()).toEqual([]);
  });
});
