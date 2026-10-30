"use client";

import { Check, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, sendFeedback } from "@/lib/api";
import type { Rating } from "@/lib/types";

type Status = "idle" | "noting" | "sending" | "sent" | "failed";

/** 👍 sends at once; 👎 first asks what was wrong (optional). */
export function useFeedback(queryId: string) {
  const [status, setStatus] = useState<Status>("idle");
  const [rating, setRating] = useState<Rating | null>(null);
  const [error, setError] = useState("");

  async function send(chosen: Rating, note?: string) {
    setRating(chosen);
    setStatus("sending");
    try {
      await sendFeedback(queryId, chosen, note);
      setStatus("sent");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Đã xảy ra lỗi.");
      setStatus("failed");
    }
  }

  function startNote() {
    setRating("down");
    setStatus("noting");
  }

  return { status, rating, error, send, startNote };
}

export type FeedbackState = ReturnType<typeof useFeedback>;

export function FeedbackButtons({ feedback }: { feedback: FeedbackState }) {
  const { status, rating, send, startNote } = feedback;
  if (status === "sent") {
    return (
      <p role="status" className="flex items-center gap-1 px-2 text-xs text-muted-foreground">
        <Check aria-hidden className="size-3.5" />
        Cảm ơn bạn đã góp ý.
      </p>
    );
  }
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-pressed={rating === "up"}
        aria-label="Câu trả lời hữu ích"
        title="Hữu ích"
        disabled={status === "sending"}
        onClick={() => void send("up")}
      >
        <ThumbsUp aria-hidden />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-pressed={rating === "down"}
        aria-label="Câu trả lời chưa tốt"
        title="Chưa tốt"
        disabled={status === "sending"}
        onClick={startNote}
      >
        <ThumbsDown aria-hidden />
      </Button>
    </>
  );
}

export function FeedbackDetails({ feedback, queryId }: { feedback: FeedbackState; queryId: string }) {
  const [note, setNote] = useState("");
  const { status, rating, error, send } = feedback;
  return (
    <>
      {(status === "noting" || (status === "failed" && rating === "down")) && (
        <form
          className="mt-2 space-y-2 rounded-lg border p-3"
          onSubmit={(event) => {
            event.preventDefault();
            void send("down", note.trim() || undefined);
          }}
        >
          <label htmlFor={`note-${queryId}`} className="text-sm font-medium">
            Góp ý (không bắt buộc)
          </label>
          <Textarea
            id={`note-${queryId}`}
            value={note}
            maxLength={1000}
            rows={2}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Câu trả lời thiếu hoặc sai ở đâu?"
          />
          <Button type="submit" size="sm">
            Gửi góp ý
          </Button>
        </form>
      )}
      {status === "failed" && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          Chưa gửi được phản hồi: {error} Vui lòng thử lại.
        </p>
      )}
    </>
  );
}
