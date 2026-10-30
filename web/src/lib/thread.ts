import { type AnswerAction, type AnswerState, answerReducer, initialAnswer } from "@/lib/answer";
import type { HistoryEntry } from "@/lib/history";

/** One question and its answer. Every question is answered on its own (no chat memory). */
export interface Turn {
  id: string;
  answer: AnswerState;
}

export type ThreadAction =
  | { type: "ask"; id: string; question: string }
  | { type: "turn"; id: string; action: AnswerAction }
  | { type: "remove"; id: string }
  | { type: "restore"; entry: HistoryEntry }
  | { type: "reset" };

export function threadReducer(turns: Turn[], action: ThreadAction): Turn[] {
  switch (action.type) {
    case "ask":
      return [
        ...turns,
        {
          id: action.id,
          answer: answerReducer(initialAnswer, { type: "start", question: action.question }),
        },
      ];
    case "turn":
      return turns.map((turn) =>
        turn.id === action.id ? { ...turn, answer: answerReducer(turn.answer, action.action) } : turn,
      );
    case "remove":
      return turns.filter((turn) => turn.id !== action.id);
    case "restore":
      return [
        {
          id: action.entry.id,
          answer: answerReducer(initialAnswer, { type: "restore", entry: action.entry }),
        },
      ];
    case "reset":
      return [];
  }
}
