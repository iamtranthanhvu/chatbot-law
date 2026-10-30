import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, ask, sendFeedback } from "@/lib/api";
import { answerReducer, initialAnswer } from "@/lib/answer";
import type { AskEvent } from "@/lib/types";

function sseResponse(body: string): Response {
  return new Response(body, { headers: { "content-type": "text/event-stream" } });
}

async function collect(question: string): Promise<AskEvent[]> {
  const events: AskEvent[] = [];
  for await (const event of ask(question)) events.push(event);
  return events;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ask", () => {
  it("posts the question and yields typed events, skipping unknown ones", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse(
        'event: meta\ndata: {"query_id":"q1","pipeline":"hybrid","intent":"lookup"}\n\n' +
          'event: ping\ndata: {}\n\n' +
          'event: token\ndata: {"delta":"Có"}\n\n',
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const events = await collect("Điều 100?");

    expect(events.map((e) => e.type)).toEqual(["meta", "token"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/ask");
    expect(JSON.parse(init.body)).toEqual({ question: "Điều 100?" });
  });

  it("turns 429 into a RATE_LIMITED error with the wait time", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "RATE_LIMITED", message: "Chậm lại" } }), {
          status: 429,
          headers: { "retry-after": "42" },
        }),
      ),
    );

    const error = await collect("q").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "RATE_LIMITED", status: 429, retryAfter: 42 });
  });

  it("reports an unreachable server as a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(collect("q")).rejects.toMatchObject({ code: "NETWORK" });
  });

  it("handles error pages that are not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>502</html>", { status: 502 })));

    await expect(collect("q")).rejects.toMatchObject({ code: "HTTP_ERROR", status: 502 });
  });
});

describe("sendFeedback", () => {
  it("sends the rating and a trimmed note", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
    vi.stubGlobal("fetch", fetchMock);

    await sendFeedback("q1", "down", "  thiếu căn cứ  ");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/queries/q1/feedback");
    expect(JSON.parse(init.body)).toEqual({ rating: "down", note: "thiếu căn cứ" });
  });
});

describe("answerReducer", () => {
  it("accumulates tokens, then takes the validated answer from done", () => {
    let state = answerReducer(initialAnswer, { type: "start", question: "q" });
    state = answerReducer(state, { type: "event", event: { type: "token", data: { delta: "Có [9]" } } });
    expect(state.text).toBe("Có [9]");

    state = answerReducer(state, {
      type: "event",
      event: {
        type: "done",
        data: {
          answer: "Có",
          citations: [],
          invalid_citations: [9],
          missing_facts: [],
          latency_ms: {},
          model: null,
          disclaimer: "x",
          cached: false,
        },
      },
    });

    expect(state.status).toBe("done");
    expect(state.text).toBe("Có");
  });

  it("starting a new question clears the previous answer", () => {
    const previous = { ...initialAnswer, status: "done" as const, text: "cũ", queryId: "q0" };

    const state = answerReducer(previous, { type: "start", question: "mới" });

    expect(state).toMatchObject({ status: "streaming", question: "mới", text: "", queryId: null });
  });
});
