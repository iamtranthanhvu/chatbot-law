"use client";

import Markdown from "react-markdown";

const CITATION = /\[(\d+)\]/g;

/** Turns "[n]" into in-page links the renderer swaps for buttons; unknown n stay plain text. */
function linkCitations(text: string, sourceCount: number): string {
  return text.replace(CITATION, (match, n: string) => {
    const number = Number(n);
    return number >= 1 && number <= sourceCount ? `[${number}](#cite-${number})` : match;
  });
}

export function AnswerText({
  text,
  sourceCount,
  onCite,
}: {
  text: string;
  sourceCount: number;
  onCite: (n: number) => void;
}) {
  return (
    <div className="answer-prose">
      {/* react-markdown never renders raw HTML from the model, so the output is safe. */}
      <Markdown
        components={{
          a({ href, children }) {
            const n = href?.startsWith("#cite-") ? Number(href.slice(6)) : null;
            if (n === null) {
              return (
                <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
                  {children}
                </a>
              );
            }
            return (
              <button
                type="button"
                onClick={() => onCite(n)}
                aria-label={`Xem nguồn ${n}`}
                className="ml-0.5 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded-full bg-accent px-1.5 align-middle text-[11px] font-semibold text-accent-foreground transition-colors hover:bg-primary hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                {n}
              </button>
            );
          },
        }}
      >
        {linkCitations(text, sourceCount)}
      </Markdown>
    </div>
  );
}
