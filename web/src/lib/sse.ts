export interface SSEMessage {
  event: string;
  data: string;
}

/**
 * Server-sent events from a fetch() body. EventSource cannot POST, so /ask is read this way.
 * Network chunks can end anywhere — mid-line or mid-character — so bytes are decoded in
 * streaming mode and only complete lines are interpreted.
 */
export async function* parseSSE(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SSEMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "";
  let data: string[] = [];

  function* dispatch(): Generator<SSEMessage> {
    if (data.length > 0) yield { event: event || "message", data: data.join("\n") };
    event = "";
    data = [];
  }

  function* consume(line: string): Generator<SSEMessage> {
    if (line === "") {
      yield* dispatch();
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // A trailing "\r" may be the first half of "\r\n"; wait for the next chunk.
      const held = buffer.endsWith("\r") ? "\r" : "";
      const lines = (held ? buffer.slice(0, -1) : buffer).split(/\r\n|\r|\n/);
      buffer = (lines.pop() ?? "") + held;
      for (const line of lines) yield* consume(line);
    }
    buffer += decoder.decode();
    const rest = buffer.replace(/\r$/, "");
    if (rest) yield* consume(rest);
    yield* dispatch();
  } finally {
    reader.releaseLock();
  }
}
