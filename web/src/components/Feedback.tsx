"use client";

import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, sendFeedback } from "@/lib/api";
import type { Rating } from "@/lib/types";

type Status = "idle" | "noting" | "sending" | "sent" | "failed";

export function Feedback({ queryId }: { queryId: string }) {
  const [status, setStatus] = useState<Status>("idle");
  const [rating, setRating] = useState<Rating | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  async function send(chosen: Rating, withNote?: string) {
    setRating(chosen);
    setStatus("sending");
    try {
      await sendFeedback(queryId, chosen, withNote);
      setStatus("sent");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Đã xảy ra lỗi.");
      setStatus("failed");
    }
  }

  if (status === "sent") {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Cảm ơn bạn đã góp ý.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Câu trả lời này có giúp ích không?</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-pressed={rating === "up"}
          aria-label="Câu trả lời hữu ích"
          disabled={status === "sending"}
          onClick={() => void send("up")}
        >
          👍 Hữu ích
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-pressed={rating === "down"}
          aria-label="Câu trả lời chưa tốt"
          disabled={status === "sending"}
          onClick={() => {
            setRating("down");
            setStatus("noting");
          }}
        >
          👎 Chưa tốt
        </Button>
      </div>
      {(status === "noting" || (status === "failed" && rating === "down")) && (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            void send("down", note.trim() || undefined);
          }}
        >
          <label htmlFor={`note-${queryId}`} className="text-sm">
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
        <Alert variant="destructive">
          <AlertDescription>Chưa gửi được phản hồi: {error} Vui lòng thử lại.</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
