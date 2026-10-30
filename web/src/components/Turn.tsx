"use client";

import { CircleAlert, RotateCcw, Scale } from "lucide-react";

import { AnswerText } from "@/components/AnswerText";
import { MessageActions } from "@/components/MessageActions";
import { SituationAnswer, splitSituation } from "@/components/SituationAnswer";
import { Sources } from "@/components/Sources";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AnswerState } from "@/lib/answer";
import type { Intent } from "@/lib/types";

const INTENT_LABELS: Record<Intent, string> = {
  situation: "Tình huống",
  lookup: "Tra cứu điều luật",
  topic_search: "Theo chủ đề",
  procedure: "Thủ tục",
  out_of_scope: "Ngoài phạm vi",
};

function progress(answer: AnswerState): string {
  if (!answer.queryId) return "Đang phân tích câu hỏi…";
  if (answer.sources.length === 0) return "Đang tìm căn cứ pháp lý…";
  return "Đang soạn câu trả lời…";
}

export function Turn({
  answer,
  onCite,
  onRetry,
}: {
  answer: AnswerState;
  onCite: (n: number) => void;
  onRetry: () => void;
}) {
  const streaming = answer.status === "streaming";
  const situation = answer.intent === "situation" ? splitSituation(answer.text) : null;

  return (
    <article className="space-y-5">
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-[0.9375rem] leading-relaxed whitespace-pre-wrap">
          {answer.question}
        </p>
      </div>

      <div className="flex gap-3">
        <span
          aria-hidden
          className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground"
        >
          <Scale className="size-4" />
        </span>
        <div className="min-w-0 flex-1 space-y-4">
          {answer.intent && (
            <Badge variant="secondary" className="font-normal">
              {INTENT_LABELS[answer.intent]}
            </Badge>
          )}

          {answer.sources.length > 0 && <Sources sources={answer.sources} onOpen={onCite} />}

          <section aria-label="Câu trả lời" aria-live="polite" aria-busy={streaming}>
            {streaming && !answer.text && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
                  <span className="relative inline-flex size-2 rounded-full bg-primary" />
                </span>
                {progress(answer)}
              </p>
            )}
            {situation ? (
              <SituationAnswer
                parts={situation}
                missingFacts={answer.done?.missing_facts ?? []}
                sourceCount={answer.sources.length}
                onCite={onCite}
              />
            ) : (
              answer.text && (
                <AnswerText text={answer.text} sourceCount={answer.sources.length} onCite={onCite} />
              )
            )}
            {answer.done && (
              <p className="mt-4 text-xs text-muted-foreground">{answer.done.disclaimer}</p>
            )}
          </section>

          {answer.error && (
            <div
              role="alert"
              className="flex flex-wrap items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
            >
              <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-destructive" />
              <p className="min-w-0 flex-1">{answer.error.message}</p>
              <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                <RotateCcw aria-hidden />
                Thử lại
              </Button>
            </div>
          )}

          {answer.done && answer.queryId && (
            <MessageActions queryId={answer.queryId} answer={answer.done.answer} />
          )}
        </div>
      </div>
    </article>
  );
}
