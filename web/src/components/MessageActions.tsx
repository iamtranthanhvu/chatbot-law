"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { FeedbackButtons, FeedbackDetails, useFeedback } from "@/components/Feedback";
import { Button } from "@/components/ui/button";

export function MessageActions({ queryId, answer }: { queryId: string; answer: string }) {
  const feedback = useFeedback(queryId);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard blocked: nothing to do, the text stays selectable
    }
  }

  return (
    <div>
      <div className="-ml-2 flex items-center gap-0.5">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={copied ? "Đã sao chép" : "Sao chép câu trả lời"}
          title="Sao chép"
          onClick={() => void copy()}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        </Button>
        <FeedbackButtons feedback={feedback} />
      </div>
      <FeedbackDetails feedback={feedback} queryId={queryId} />
    </div>
  );
}
