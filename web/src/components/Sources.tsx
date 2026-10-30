"use client";

import type { SourcePayload } from "@/lib/types";

export function sourceLabel(source: SourcePayload): string {
  return source.khoan ? `Điều ${source.dieu}, khoản ${source.khoan}` : `Điều ${source.dieu}`;
}

export function Sources({
  sources,
  onOpen,
}: {
  sources: SourcePayload[];
  onOpen: (n: number) => void;
}) {
  return (
    <section aria-labelledby="sources-heading" className="space-y-2">
      <h2 id="sources-heading" className="text-sm font-semibold text-muted-foreground">
        Căn cứ được dùng
      </h2>
      <ol aria-label="Căn cứ pháp lý" className="space-y-2">
        {sources.map((source) => (
          <li key={source.n} id={`source-${source.n}`}>
            <button
              type="button"
              onClick={() => onOpen(source.n)}
              className="w-full rounded-lg border bg-card p-3 text-left text-sm transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <span className="font-medium">
                [{source.n}] {sourceLabel(source)}
              </span>
              <span className="text-muted-foreground"> · {source.title}</span>
              <span className="mt-1 line-clamp-2 block text-muted-foreground">
                {source.snippet}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
