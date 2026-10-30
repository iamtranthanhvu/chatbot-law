import { describe, expect, it } from "vitest";

import { threadReducer } from "@/lib/thread";
import type { HistoryEntry } from "@/lib/history";

const ENTRY: HistoryEntry = {
  id: "q-old",
  question: "Điều 100?",
  answer: "Trả lời cũ [1].",
  intent: "lookup",
  sources: [],
  missingFacts: [],
  disclaimer: "Tham khảo.",
  askedAt: "2026-10-30T10:00:00.000Z",
};

describe("threadReducer", () => {
  it("adds each question as a new turn and routes events to it", () => {
    let turns = threadReducer([], { type: "ask", id: "t1", question: "câu 1" });
    turns = threadReducer(turns, { type: "ask", id: "t2", question: "câu 2" });
    turns = threadReducer(turns, {
      type: "turn",
      id: "t1",
      action: { type: "event", event: { type: "token", data: { delta: "một" } } },
    });

    expect(turns.map((t) => [t.id, t.answer.question, t.answer.text])).toEqual([
      ["t1", "câu 1", "một"],
      ["t2", "câu 2", ""],
    ]);
    expect(turns[1].answer.status).toBe("streaming");
  });

  it("removes a turn (retrying a failed question)", () => {
    const turns = threadReducer(threadReducer([], { type: "ask", id: "t1", question: "q" }), {
      type: "remove",
      id: "t1",
    });

    expect(turns).toEqual([]);
  });

  it("opening a history entry shows it alone, and reset starts over", () => {
    const asked = threadReducer([], { type: "ask", id: "t1", question: "q" });

    const restored = threadReducer(asked, { type: "restore", entry: ENTRY });
    expect(restored).toHaveLength(1);
    expect(restored[0].answer).toMatchObject({ status: "done", text: "Trả lời cũ [1].", queryId: "q-old" });

    expect(threadReducer(restored, { type: "reset" })).toEqual([]);
  });
});
