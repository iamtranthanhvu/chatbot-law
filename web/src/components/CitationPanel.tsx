"use client";

import { useEffect, useState } from "react";

import { sourceLabel } from "@/components/Sources";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ApiError, getChunk } from "@/lib/api";
import type { ChunkDetail, SourcePayload } from "@/lib/types";

type Loaded =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; chunks: ChunkDetail[] };

/** Verbatim text of one source: every chunk of the article that was given to the model. */
export function CitationPanel({
  source,
  onClose,
}: {
  source: SourcePayload | null;
  onClose: () => void;
}) {
  // Results are tagged with their source, so a newly opened source reads as loading without
  // resetting state inside the effect.
  const [result, setResult] = useState<{ source: SourcePayload; loaded: Loaded } | null>(null);
  const loaded: Loaded =
    result && result.source === source ? result.loaded : { status: "loading" };

  useEffect(() => {
    if (!source) return;
    const controller = new AbortController();
    Promise.all(source.chunk_ids.map((id) => getChunk(id, controller.signal)))
      .then((chunks) => setResult({ source, loaded: { status: "ready", chunks } }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof ApiError ? error.message : "Không tải được nguyên văn, vui lòng thử lại.";
        setResult({ source, loaded: { status: "error", message } });
      });
    return () => controller.abort();
  }, [source]);

  const first = loaded.status === "ready" ? loaded.chunks[0] : undefined;

  return (
    <Sheet open={source !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="pr-10">
          <SheetTitle>
            {first
              ? `Điều ${first.dieu}. ${first.article_title}`
              : source && `${sourceLabel(source)} · ${source.title}`}
          </SheetTitle>
          <SheetDescription>
            {first ? `${first.document_name} (${first.so_hieu}) · ${chapterOf(first)}` : "Đang tải…"}
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6">
          {loaded.status === "error" && (
            <Alert variant="destructive">
              <AlertDescription>{loaded.message}</AlertDescription>
            </Alert>
          )}
          {loaded.status === "ready" &&
            loaded.chunks.map((chunk, i) => (
              <div key={chunk.id}>
                {i > 0 && <p className="my-2 text-center text-muted-foreground">…</p>}
                <p className="leading-relaxed whitespace-pre-line">{chunk.text}</p>
              </div>
            ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function chapterOf(chunk: ChunkDetail): string {
  const parts = [];
  if (chunk.chapter_number) parts.push(`Chương ${chunk.chapter_number}. ${chunk.chapter_title ?? ""}`.trim());
  if (chunk.section_number) parts.push(`Mục ${chunk.section_number}. ${chunk.section_title ?? ""}`.trim());
  return parts.join(" › ");
}
