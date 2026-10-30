"use client";

import { useReducer, useRef, useState } from "react";

import { AnswerText } from "@/components/AnswerText";
import { CitationPanel } from "@/components/CitationPanel";
import { Feedback } from "@/components/Feedback";
import { History } from "@/components/History";
import { SituationAnswer, splitSituation } from "@/components/SituationAnswer";
import { Sources } from "@/components/Sources";
import { Suggestions } from "@/components/Suggestions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { answerReducer, initialAnswer } from "@/lib/answer";
import { ApiError, ask } from "@/lib/api";
import { addEntry } from "@/lib/history";
import type { AskEvent, DonePayload, ErrorPayload } from "@/lib/types";

export const MAX_QUESTION_CHARS = 1000;

function toUserError(error: unknown): ErrorPayload {
  if (error instanceof ApiError) {
    if (error.code === "RATE_LIMITED") {
      const wait = error.retryAfter ? ` sau ${error.retryAfter} giây` : " sau ít phút";
      return {
        code: error.code,
        message: `Bạn đã hỏi quá nhiều trong thời gian ngắn. Vui lòng thử lại${wait}.`,
      };
    }
    if (error.code === "VALIDATION_ERROR") {
      return {
        code: error.code,
        message: `Câu hỏi cần có nội dung và dài tối đa ${MAX_QUESTION_CHARS.toLocaleString("vi-VN")} ký tự.`,
      };
    }
    return { code: error.code, message: error.message };
  }
  return { code: "UNKNOWN", message: "Đã xảy ra lỗi, vui lòng thử lại." };
}

export function Chat() {
  const [question, setQuestion] = useState("");
  const [state, dispatch] = useReducer(answerReducer, initialAnswer);
  const [openSource, setOpenSource] = useState<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const streaming = state.status === "streaming";
  const trimmed = question.trim();

  async function submit() {
    if (!trimmed || streaming) return;
    const current = new AbortController();
    controller.current = current;
    dispatch({ type: "start", question: trimmed });
    const seen: { meta?: AskEvent; sources?: AskEvent; done?: DonePayload } = {};
    try {
      for await (const event of ask(trimmed, current.signal)) {
        dispatch({ type: "event", event });
        if (event.type === "done") seen.done = event.data;
        else if (event.type === "meta" || event.type === "sources") seen[event.type] = event;
      }
      dispatch({ type: "stop" });
      remember(trimmed, seen);
    } catch (error) {
      if (current.signal.aborted) dispatch({ type: "stop" });
      else dispatch({ type: "fail", error: toUserError(error) });
    }
  }

  function stop() {
    controller.current?.abort();
  }

  const situation = state.intent === "situation" ? splitSituation(state.text) : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_16rem]">
      <div className="flex min-w-0 flex-col gap-6">
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label htmlFor="question" className="text-sm font-medium">
            Câu hỏi của bạn
          </label>
          <Textarea
            id="question"
            ref={input}
            value={question}
            maxLength={MAX_QUESTION_CHARS}
            rows={3}
            placeholder="Ví dụ: Tôi muốn tách thửa đất ở thì cần điều kiện gì?"
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void submit();
              }
            }}
            aria-describedby="question-hint"
            className="resize-y text-base"
          />
          <div className="flex items-center justify-between gap-3">
            <p id="question-hint" className="text-xs text-muted-foreground">
              Enter để gửi, Shift + Enter để xuống dòng · {question.length}/
              {MAX_QUESTION_CHARS.toLocaleString("vi-VN")}
            </p>
            {streaming ? (
              <Button type="button" variant="outline" onClick={stop}>
                Dừng
              </Button>
            ) : (
              <Button type="submit" disabled={!trimmed}>
                Hỏi
              </Button>
            )}
          </div>
        </form>

        {state.status === "idle" ? (
          <Suggestions
            onPick={(picked) => {
              setQuestion(picked);
              input.current?.focus();
            }}
          />
        ) : (
          <div className="space-y-5">
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Câu hỏi:</span> {state.question}
            </p>

            {state.error && (
              <Alert variant="destructive">
                <AlertTitle>Chưa trả lời được</AlertTitle>
                <AlertDescription>{state.error.message}</AlertDescription>
              </Alert>
            )}

            <section
              aria-label="Câu trả lời"
              aria-live="polite"
              aria-busy={streaming}
              className="min-h-6"
            >
              {streaming && !state.text && (
                <p className="text-sm text-muted-foreground">Đang tìm căn cứ và soạn câu trả lời…</p>
              )}
              {situation ? (
                <SituationAnswer
                  parts={situation}
                  missingFacts={state.done?.missing_facts ?? []}
                  sourceCount={state.sources.length}
                  onCite={setOpenSource}
                />
              ) : (
                state.text && (
                  <AnswerText
                    text={state.text}
                    sourceCount={state.sources.length}
                    onCite={setOpenSource}
                  />
                )
              )}
              {state.done && (
                <p className="mt-4 text-xs text-muted-foreground">{state.done.disclaimer}</p>
              )}
            </section>

            {state.done && state.queryId && <Feedback key={state.queryId} queryId={state.queryId} />}

            {state.sources.length > 0 && <Sources sources={state.sources} onOpen={setOpenSource} />}

            <CitationPanel
              source={state.sources.find((s) => s.n === openSource) ?? null}
              onClose={() => setOpenSource(null)}
            />
          </div>
        )}
      </div>
      <aside className="lg:border-l lg:pl-6">
        <History
          activeId={state.queryId}
          onOpen={(entry) => {
            controller.current?.abort();
            setOpenSource(null);
            dispatch({ type: "restore", entry });
          }}
        />
      </aside>
    </div>
  );
}

function remember(
  question: string,
  seen: { meta?: AskEvent; sources?: AskEvent; done?: DonePayload },
): void {
  if (seen.meta?.type !== "meta" || !seen.done) return;
  addEntry({
    id: seen.meta.data.query_id,
    question,
    answer: seen.done.answer,
    intent: seen.meta.data.intent,
    sources: seen.sources?.type === "sources" ? seen.sources.data : [],
    missingFacts: seen.done.missing_facts,
    disclaimer: seen.done.disclaimer,
    askedAt: new Date().toISOString(),
  });
}
