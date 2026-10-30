"use client";

import { ArrowUp, Square } from "lucide-react";
import { type Ref, useState } from "react";

import { Button } from "@/components/ui/button";

export const MAX_QUESTION_CHARS = 1000;

export function Composer({
  busy,
  onAsk,
  onStop,
  inputRef,
}: {
  busy: boolean;
  onAsk: (question: string) => void;
  onStop: () => void;
  inputRef?: Ref<HTMLTextAreaElement>;
}) {
  const [question, setQuestion] = useState("");
  const trimmed = question.trim();
  const nearLimit = question.length > MAX_QUESTION_CHARS * 0.8;

  function submit() {
    if (!trimmed || busy) return;
    onAsk(trimmed);
    setQuestion("");
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="rounded-xl border bg-card shadow-sm transition-colors focus-within:border-primary/50 focus-within:ring-3 focus-within:ring-ring/20"
    >
      <label htmlFor="question" className="sr-only">
        Câu hỏi của bạn
      </label>
      <textarea
        id="question"
        ref={inputRef}
        value={question}
        maxLength={MAX_QUESTION_CHARS}
        rows={1}
        placeholder="Hỏi về đất đai, ví dụ: Tách thửa đất ở cần điều kiện gì?"
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
        aria-describedby="question-hint"
        className="field-sizing-content block max-h-52 min-h-14 w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-base outline-none placeholder:text-muted-foreground"
      />
      <div className="flex items-center justify-between gap-3 px-3 pb-2.5">
        <p id="question-hint" className="text-xs text-muted-foreground">
          <span className="hidden sm:inline">Enter để gửi · Shift + Enter xuống dòng</span>
          {nearLimit && (
            <span>
              {" "}
              · {question.length}/{MAX_QUESTION_CHARS.toLocaleString("vi-VN")} ký tự
            </span>
          )}
        </p>
        {busy ? (
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="rounded-full"
            aria-label="Dừng"
            title="Dừng trả lời"
            onClick={onStop}
          >
            <Square aria-hidden className="size-3 fill-current" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            className="rounded-full"
            aria-label="Hỏi"
            title="Gửi câu hỏi"
            disabled={!trimmed}
          >
            <ArrowUp aria-hidden />
          </Button>
        )}
      </div>
    </form>
  );
}
