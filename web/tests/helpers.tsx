import { act } from "@testing-library/react";

import type { AskEvent, DonePayload, SourcePayload } from "@/lib/types";

export const SOURCE: SourcePayload = {
  n: 1,
  chunk_id: "c1",
  chunk_ids: ["c1"],
  so_hieu: "45/2013/QH13",
  dieu: "188",
  khoan: "1",
  title: "Điều kiện thực hiện các quyền chuyển nhượng",
  snippet: "1. Người sử dụng đất được thực hiện các quyền…",
  score: 0.9,
};

export const DONE: DonePayload = {
  answer: "Không được, vì chưa có Giấy chứng nhận [1].",
  citations: [1],
  invalid_citations: [],
  missing_facts: [],
  latency_ms: {},
  model: "m",
  disclaimer: "Thông tin chỉ mang tính tham khảo, không thay thế tư vấn pháp lý.",
  cached: false,
};

/** An ask() whose events the test releases one at a time. */
export function controlledAsk() {
  const queue: AskEvent[] = [];
  let wake: (() => void) | null = null;
  let finished = false;
  async function* generate(): AsyncGenerator<AskEvent> {
    for (;;) {
      while (queue.length) yield queue.shift()!;
      if (finished) return;
      await new Promise<void>((resolve) => (wake = resolve));
    }
  }
  return {
    generate,
    async push(...events: AskEvent[]) {
      await act(async () => {
        queue.push(...events);
        wake?.();
        await new Promise((r) => setTimeout(r, 0));
      });
    },
    async end() {
      await act(async () => {
        finished = true;
        wake?.();
        await new Promise((r) => setTimeout(r, 0));
      });
    },
  };
}

