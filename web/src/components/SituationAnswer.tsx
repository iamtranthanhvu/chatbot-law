"use client";

import { useId } from "react";

import { AnswerText } from "@/components/AnswerText";

const HEADING = /^\*\*(Kết luận|Giải thích|Thông tin nên bổ sung|Căn cứ pháp lý):\*\*/gm;

export interface SituationParts {
  conclusion: string;
  facts: string[];
  body: string;
}

/**
 * The situation prompt asks for four bold-headed sections. The conclusion and the facts to
 * add get their own blocks; the other sections stay in the body. Null when the model did not
 * follow the format, so the answer is shown as written.
 */
export function splitSituation(text: string): SituationParts | null {
  const matches = [...text.matchAll(HEADING)];
  if (!matches.some((m) => m[1] === "Kết luận")) return null;
  let conclusion = "";
  let facts: string[] = [];
  const body: string[] = [];
  const lead = text.slice(0, matches[0].index).trim();
  if (lead) body.push(lead);
  matches.forEach((match, i) => {
    const start = match.index + match[0].length;
    const raw = text.slice(start, matches[i + 1]?.index ?? text.length).trimEnd();
    if (match[1] === "Kết luận") conclusion = raw.trim();
    else if (match[1] === "Thông tin nên bổ sung") facts = bulletItems(raw);
    else body.push(`**${match[1]}:**${raw}`);
  });
  return { conclusion, facts, body: body.join("\n") };
}

function bulletItems(raw: string): string[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^[-*•]\s+/.test(line))
    .map((line) => line.replace(/^[-*•]\s+/, ""))
    .filter((item) => item.toLowerCase() !== "không có");
}

export function SituationAnswer({
  parts,
  missingFacts,
  sourceCount,
  onCite,
}: {
  parts: SituationParts;
  missingFacts: string[];
  sourceCount: number;
  onCite: (n: number) => void;
}) {
  const conclusionId = useId();
  const factsId = useId();
  const facts = missingFacts.length > 0 ? missingFacts : parts.facts;
  return (
    <div className="space-y-4">
      <section
        aria-labelledby={conclusionId}
        className="rounded-lg border border-l-4 border-l-primary bg-muted/60 p-4"
      >
        <h3 id={conclusionId} className="mb-1 text-sm font-semibold">
          Kết luận
        </h3>
        <AnswerText text={parts.conclusion} sourceCount={sourceCount} onCite={onCite} />
      </section>
      {parts.body && <AnswerText text={parts.body} sourceCount={sourceCount} onCite={onCite} />}
      {facts.length > 0 && (
        <section aria-labelledby={factsId} className="rounded-lg border p-4">
          <h3 id={factsId} className="mb-1 text-sm font-semibold">
            Thông tin nên bổ sung
          </h3>
          <p className="mb-2 text-sm text-muted-foreground">
            Kết luận có thể khác nếu bạn cho biết thêm:
          </p>
          <ul className="list-disc space-y-1 pl-5">
            {facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
