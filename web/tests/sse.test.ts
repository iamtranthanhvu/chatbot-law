import { describe, expect, it } from "vitest";

import { parseSSE, type SSEMessage } from "@/lib/sse";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SSEMessage[]> {
  const messages: SSEMessage[] = [];
  for await (const message of parseSSE(stream)) messages.push(message);
  return messages;
}

describe("parseSSE", () => {
  it("reads named events with JSON data", async () => {
    const messages = await collect(
      streamOf('event: meta\ndata: {"query_id":"q1"}\n\nevent: token\ndata: {"delta":"Có"}\n\n'),
    );

    expect(messages).toEqual([
      { event: "meta", data: '{"query_id":"q1"}' },
      { event: "token", data: '{"delta":"Có"}' },
    ]);
  });

  it("joins an event cut in the middle across two network chunks", async () => {
    const messages = await collect(
      streamOf('event: tok', 'en\ndata: {"delta":"đất', ' đai"}\n', "\n"),
    );

    expect(messages).toEqual([{ event: "token", data: '{"delta":"đất đai"}' }]);
  });

  it("decodes a multi-byte character split between chunks", async () => {
    const bytes = new TextEncoder().encode('event: token\ndata: {"delta":"Điều"}\n\n');
    const cut = bytes.indexOf(0x90); // second byte of "Đ"
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, cut));
        controller.enqueue(bytes.slice(cut));
        controller.close();
      },
    });

    expect(await collect(stream)).toEqual([{ event: "token", data: '{"delta":"Điều"}' }]);
  });

  it("accepts CRLF line endings, comments and multi-line data", async () => {
    const messages = await collect(
      streamOf(": keep-alive\r\n\r\nevent: done\r\ndata: line 1\r\ndata: line 2\r\n\r\n"),
    );

    expect(messages).toEqual([{ event: "done", data: "line 1\nline 2" }]);
  });

  it("does not split an event when a CRLF pair is cut between chunks", async () => {
    const messages = await collect(streamOf("event: meta\r", "\ndata: a\r", "\n\r\n"));

    expect(messages).toEqual([{ event: "meta", data: "a" }]);
  });

  it("defaults the event name to message and flushes a final event without a blank line", async () => {
    expect(await collect(streamOf("data: x"))).toEqual([{ event: "message", data: "x" }]);
  });
});
