import { parseSSE } from "@/lib/sse";
import type { AskEvent, ChunkDetail, Rating } from "@/lib/types";

/** Same-origin by default: Next rewrites /api in development, Caddy routes it in production. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1";

const ASK_EVENTS = new Set(["meta", "sources", "token", "done", "error"]);

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status = 0,
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const NETWORK_MESSAGE = "Không kết nối được máy chủ. Vui lòng kiểm tra mạng và thử lại.";

async function request(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("NETWORK", NETWORK_MESSAGE);
  }
  if (!response.ok) throw await toApiError(response);
  return response;
}

async function toApiError(response: Response): Promise<ApiError> {
  const retryAfter = Number(response.headers.get("retry-after")) || undefined;
  try {
    const body = (await response.json()) as { error?: { code?: string; message?: string } };
    if (body.error?.code) {
      return new ApiError(
        body.error.code,
        body.error.message ?? "Đã xảy ra lỗi.",
        response.status,
        retryAfter,
      );
    }
  } catch {
    // not our JSON error shape (a proxy error page, for example)
  }
  return new ApiError("HTTP_ERROR", "Máy chủ đang gặp sự cố, vui lòng thử lại sau.", response.status);
}

export async function* ask(question: string, signal?: AbortSignal): AsyncGenerator<AskEvent> {
  const response = await request("/ask", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.body) throw new ApiError("NETWORK", NETWORK_MESSAGE);
  try {
    for await (const message of parseSSE(response.body)) {
      if (ASK_EVENTS.has(message.event)) {
        yield { type: message.event, data: JSON.parse(message.data) } as AskEvent;
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("NETWORK", "Mất kết nối khi đang nhận câu trả lời. Vui lòng thử lại.");
  }
}

export async function getChunk(id: string, signal?: AbortSignal): Promise<ChunkDetail> {
  const response = await request(`/chunks/${encodeURIComponent(id)}`, { signal });
  return (await response.json()) as ChunkDetail;
}

export async function sendFeedback(queryId: string, rating: Rating, note?: string): Promise<void> {
  await request(`/queries/${encodeURIComponent(queryId)}/feedback`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ rating, note: note?.trim() || null }),
  });
}
