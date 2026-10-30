"use client";

import type { SourcePayload } from "@/lib/types";

export function sourceLabel(source: SourcePayload): string {
  return source.khoan ? `Điều ${source.dieu}, khoản ${source.khoan}` : `Điều ${source.dieu}`;
}

/** The legal bases of one answer, as a strip of cards above it. */
export function Sources({
  sources,
  onOpen,
}: {
  sources: SourcePayload[];
  onOpen: (n: number) => void;
}) {
  return (
    <div className="min-w-0">
      <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        Căn cứ · {sources.length}
      </p>
      <ol aria-label="Căn cứ pháp lý" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {sources.map((source) => (
          <li key={source.n} className="w-52 shrink-0">
            <button
              type="button"
              onClick={() => onOpen(source.n)}
              className="flex h-full w-full flex-col gap-1 rounded-lg border bg-card p-2.5 text-left transition-colors hover:border-primary/40 hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <span className="flex items-center gap-1.5 text-xs font-semibold">
                <span className="inline-flex size-4.5 shrink-0 items-center justify-center rounded-full bg-accent text-[10px] text-accent-foreground">
                  {source.n}
                </span>
                <span className="truncate">{sourceLabel(source)}</span>
              </span>
              <span className="line-clamp-2 text-xs leading-snug text-muted-foreground">
                {source.title}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
