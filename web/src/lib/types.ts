export type Intent = "situation" | "lookup" | "topic_search" | "procedure" | "out_of_scope";

export interface MetaPayload {
  query_id: string;
  pipeline: string;
  intent: Intent | null;
}

export interface SourcePayload {
  n: number;
  chunk_id: string;
  chunk_ids: string[];
  so_hieu: string;
  dieu: string;
  khoan: string;
  title: string;
  snippet: string;
  score: number;
}

export interface DonePayload {
  answer: string;
  citations: number[];
  invalid_citations: number[];
  missing_facts: string[];
  latency_ms: Record<string, number>;
  model: string | null;
  disclaimer: string;
  cached: boolean;
}

export interface ErrorPayload {
  code: string;
  message: string;
}

export type AskEvent =
  | { type: "meta"; data: MetaPayload }
  | { type: "sources"; data: SourcePayload[] }
  | { type: "token"; data: { delta: string } }
  | { type: "done"; data: DonePayload }
  | { type: "error"; data: ErrorPayload };

export interface ChunkDetail {
  id: string;
  so_hieu: string;
  document_name: string;
  path: string;
  chapter_number: string | null;
  chapter_title: string | null;
  section_number: string | null;
  section_title: string | null;
  dieu: string;
  article_title: string;
  khoan: number[];
  diem: string[];
  location: string;
  text: string;
  valid_from: string | null;
  valid_to: string | null;
}

export type Rating = "up" | "down";
