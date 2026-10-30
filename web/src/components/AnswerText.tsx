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
    <div className="answer-markdown space-y-3 leading-relaxed">
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
                className="mx-0.5 rounded px-1 align-baseline text-sm font-medium text-blue-700 underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:outline-none dark:text-blue-300"
              >
                [{n}]
              </button>
            );
          },
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
        }}
      >
        {linkCitations(text, sourceCount)}
      </Markdown>
    </div>
  );
}
