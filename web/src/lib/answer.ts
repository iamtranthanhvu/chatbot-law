import type { HistoryEntry } from "@/lib/history";
import type { AskEvent, DonePayload, ErrorPayload, Intent, SourcePayload } from "@/lib/types";

export interface AnswerState {
  status: "idle" | "streaming" | "done" | "error";
  question: string;
  queryId: string | null;
  intent: Intent | null;
  sources: SourcePayload[];
  text: string;
  done: DonePayload | null;
  error: ErrorPayload | null;
}

export const initialAnswer: AnswerState = {
  status: "idle",
  question: "",
  queryId: null,
  intent: null,
  sources: [],
  text: "",
  done: null,
  error: null,
};

export type AnswerAction =
  | { type: "start"; question: string }
  | { type: "event"; event: AskEvent }
  | { type: "fail"; error: ErrorPayload }
  | { type: "stop" }
  | { type: "restore"; entry: HistoryEntry };

export function answerReducer(state: AnswerState, action: AnswerAction): AnswerState {
  switch (action.type) {
    case "start":
      return { ...initialAnswer, status: "streaming", question: action.question };
    case "fail":
      return { ...state, status: "error", error: action.error };
    case "stop":
      return state.status === "streaming" ? { ...state, status: "done" } : state;
    case "event":
      return applyEvent(state, action.event);
    case "restore":
      return restore(action.entry);
  }
}

function applyEvent(state: AnswerState, event: AskEvent): AnswerState {
  switch (event.type) {
    case "meta":
      return { ...state, queryId: event.data.query_id, intent: event.data.intent };
    case "sources":
      return { ...state, sources: event.data };
    case "token":
      return { ...state, text: state.text + event.data.delta };
    case "done":
      // The final answer has invalid citations removed, so it replaces the streamed text.
      return { ...state, status: "done", done: event.data, text: event.data.answer };
    case "error":
      return { ...state, status: "error", error: event.data };
  }
}

function restore(entry: HistoryEntry): AnswerState {
  return {
    status: "done",
    question: entry.question,
    queryId: entry.id,
    intent: entry.intent,
    sources: entry.sources,
    text: entry.answer,
    done: {
      answer: entry.answer,
      citations: [],
      invalid_citations: [],
      missing_facts: entry.missingFacts,
      latency_ms: {},
      model: null,
      disclaimer: entry.disclaimer,
      cached: true,
    },
    error: null,
  };
}
