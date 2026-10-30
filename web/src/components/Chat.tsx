"use client";

import { Menu, SquarePen } from "lucide-react";
import { useEffect, useReducer, useRef, useState } from "react";

import { CitationPanel } from "@/components/CitationPanel";
import { Composer } from "@/components/Composer";
import { Brand, Sidebar } from "@/components/Sidebar";
import { Suggestions } from "@/components/Suggestions";
import { Turn } from "@/components/Turn";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { ApiError, ask } from "@/lib/api";
import { type HistoryEntry, addEntry } from "@/lib/history";
import { threadReducer } from "@/lib/thread";
import type { AskEvent, DonePayload, ErrorPayload } from "@/lib/types";

export { MAX_QUESTION_CHARS } from "@/components/Composer";

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
      return { code: error.code, message: "Câu hỏi cần có nội dung và dài tối đa 1.000 ký tự." };
    }
    return { code: error.code, message: error.message };
  }
  return { code: "UNKNOWN", message: "Đã xảy ra lỗi, vui lòng thử lại." };
}

export function Chat() {
  const [turns, dispatch] = useReducer(threadReducer, []);
  const [cited, setCited] = useState<{ turnId: string; n: number } | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const nextId = useRef(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const followOutput = useRef(true);

  const busy = turns.some((turn) => turn.answer.status === "streaming");
  const last = turns.at(-1);
  const citedSource = cited
    ? turns.find((t) => t.id === cited.turnId)?.answer.sources.find((s) => s.n === cited.n)
    : undefined;

  // Keep the newest text in view while it streams, unless the reader scrolled up.
  useEffect(() => {
    const box = scroller.current;
    if (box && followOutput.current) box.scrollTop = box.scrollHeight;
  }, [turns]);

  async function submit(question: string) {
    if (busy) return;
    const id = `turn-${++nextId.current}`;
    const current = new AbortController();
    controller.current = current;
    followOutput.current = true;
    dispatch({ type: "ask", id, question });
    const seen: { meta?: AskEvent; sources?: AskEvent; done?: DonePayload } = {};
    try {
      for await (const event of ask(question, current.signal)) {
        dispatch({ type: "turn", id, action: { type: "event", event } });
        if (event.type === "done") seen.done = event.data;
        else if (event.type === "meta" || event.type === "sources") seen[event.type] = event;
      }
      dispatch({ type: "turn", id, action: { type: "stop" } });
      remember(question, seen);
    } catch (error) {
      dispatch({
        type: "turn",
        id,
        action: current.signal.aborted
          ? { type: "stop" }
          : { type: "fail", error: toUserError(error) },
      });
    }
  }

  function startOver() {
    controller.current?.abort();
    setCited(null);
    setNavOpen(false);
    dispatch({ type: "reset" });
    input.current?.focus();
  }

  function open(entry: HistoryEntry) {
    controller.current?.abort();
    setCited(null);
    setNavOpen(false);
    dispatch({ type: "restore", entry });
  }

  const sidebar = (
    <Sidebar activeId={last?.answer.queryId ?? null} onNew={startOver} onOpen={open} />
  );
  const composer = (
    <Composer
      busy={busy}
      inputRef={input}
      onAsk={(question) => void submit(question)}
      onStop={() => controller.current?.abort()}
    />
  );

  return (
    <div className="flex h-dvh overflow-hidden">
      <aside className="hidden w-72 shrink-0 border-r bg-sidebar md:block">{sidebar}</aside>

      <Sheet open={navOpen} onOpenChange={setNavOpen}>
        <SheetContent side="left" className="w-72 bg-sidebar p-0 md:hidden">
          <SheetTitle className="sr-only">Menu</SheetTitle>
          <SheetDescription className="sr-only">
            Lịch sử câu hỏi và thông tin dữ liệu
          </SheetDescription>
          {sidebar}
        </SheetContent>
      </Sheet>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b px-2 py-2 md:hidden">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Mở menu"
            onClick={() => setNavOpen(true)}
          >
            <Menu aria-hidden />
          </Button>
          <Brand />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Câu hỏi mới"
            onClick={startOver}
          >
            <SquarePen aria-hidden />
          </Button>
        </header>

        {turns.length === 0 ? (
          <div className="flex flex-1 flex-col items-center overflow-y-auto px-4 py-10 sm:justify-center">
            <div className="w-full max-w-2xl space-y-6">
              <div className="space-y-2 text-center">
                <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                  Bạn cần hỏi gì về đất đai?
                </h1>
                <p className="text-sm text-muted-foreground">
                  Mô tả tình huống của bạn hoặc tra cứu một Điều luật. Mỗi câu trả lời đều kèm căn
                  cứ trong Luật Đất đai 2013.
                </p>
              </div>
              {composer}
              <Suggestions onPick={(question) => void submit(question)} />
              <p className="text-center text-xs text-muted-foreground">
                Vui lòng không nhập thông tin cá nhân (họ tên, số CCCD, số điện thoại…).
              </p>
            </div>
          </div>
        ) : (
          <>
            <div
              ref={scroller}
              onScroll={(event) => {
                const box = event.currentTarget;
                followOutput.current = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
              }}
              className="flex-1 overflow-y-auto"
            >
              <div className="mx-auto w-full max-w-3xl space-y-10 px-4 py-8">
                <h1 className="sr-only">Hỏi đáp Luật Đất đai</h1>
                {turns.map((turn) => (
                  <Turn
                    key={turn.id}
                    answer={turn.answer}
                    onCite={(n) => setCited({ turnId: turn.id, n })}
                    onRetry={() => {
                      dispatch({ type: "remove", id: turn.id });
                      void submit(turn.answer.question);
                    }}
                  />
                ))}
              </div>
            </div>
            <div className="border-t bg-background px-4 py-3">
              <div className="mx-auto w-full max-w-3xl space-y-2">
                {composer}
                <p className="text-center text-[11px] text-muted-foreground">
                  Mỗi câu hỏi được trả lời độc lập theo Luật Đất đai 2013 · Chỉ mang tính tham khảo
                </p>
              </div>
            </div>
          </>
        )}
      </main>

      <CitationPanel source={citedSource ?? null} onClose={() => setCited(null)} />
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
