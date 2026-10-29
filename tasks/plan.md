# Implementation Plan: Law QA — Branch 1 (Hybrid RAG, Luật Đất đai 45/2013)

Spec: [`SPEC.md`](../SPEC.md) (v5). Task chi tiết: [`tasks/todo.md`](todo.md).

## Overview

Xây hệ thống hỏi đáp Luật Đất đai 2013 chạy được thật: nạp DOCX bằng CLI → Postgres + Qdrant → hybrid retrieval (dense BGE-M3 + BM25 tiếng Việt + RRF) → rerank → sinh câu trả lời có trích dẫn (Qwen3 qua API OpenAI-compatible) → API SSE → web Next.js → triển khai Docker Compose trên máy GPU. Dev trên Mac M1: LLM qua Ollama và model-server chạy native để dùng GPU Metal.

Chiến lược: **làm phần rủi ro nhất trước** (parse file luật thật), dựng **walking skeleton** `lawqa ask` chạy end-to-end bằng CLI càng sớm càng tốt, dựng **eval trước khi tối ưu** để mọi cải tiến (rerank, query understanding) đều đo được, sau đó mới tới API, web, production.

## Architecture Decisions

| Quyết định | Lý do |
|---|---|
| Monorepo: `backend/` (package `lawqa`), `model-server/`, `web/` | 3 đơn vị deploy độc lập, chung một repo để branch 2/3 checkout cả hệ thống |
| Parser dựa trên text, không dựa style Word | File 2013 dùng style `NormalWeb`, file 2024 không có style; Chương đánh số Ả Rập vs La Mã |
| Đếm token chunk bằng tokenizer của BGE-M3 (`tokenizers`, chỉ tải `tokenizer.json`) | Giới hạn 512 token phải khớp model embedding; không cần kéo PyTorch vào backend |
| BM25 tự tính TF phía Python, IDF do Qdrant (`modifier: idf`) | Qdrant không có tokenizer tiếng Việt; tự kiểm soát tokenizer (âm tiết + bigram + định danh pháp lý) |
| Model-server tách riêng, backend gọi qua HTTP | Backend không phụ thuộc PyTorch; dev chạy native MPS, prod chạy CUDA; test backend dùng fake |
| `RAGPipeline` interface từ task đầu của retrieval | Branch 2/3 thay pipeline, giữ nguyên API/web/eval |
| Eval dựng trước rerank & query understanding | Chứng minh bằng số từng thành phần có đóng góp (ablation trong spec) |
| `valid_from`/`valid_to` + filter hiệu lực có ngay | Chừa chỗ cho giai đoạn cập nhật văn bản (SPEC mục 13) mà không đổi retrieval |
| Seed eval set tự soạn (~30 câu, người duyệt) dùng tạm khi chưa có golden set | Không chặn Phase 4 vì open question về golden set |

## Dependency Graph

```
T1 repo + infra dev
 ├─▶ T2 docx/normalize/metadata ─▶ T3 parser + integrity + dry-run ─▶ T4 chunker ─┐
 ├─▶ T5 model-server (song song T2–T4) ───────────────────────────────────────────┤
 └─▶ T6 DB schema + persist (cần T4) ─▶ T7 BM25 encoder ─▶ T8 indexer + ingest ◀──┘
                                                              │
                         T9 hybrid retrieval ◀────────────────┘
                         T10 LLM client + citations (song song T9)
                         T11 pipeline + `lawqa ask`  ◀── T9, T10
                              │
            T12 eval retrieval ─▶ T13 eval generation
                              │
   T14 rerank ─ T15 citation lookup ─ T16 synonyms + multi-query ─ T17 understanding ─ T18 intent prompts
                              │
            T19 API read endpoints ─▶ T20 /ask SSE + log + feedback ─▶ T21 rate limit/concurrency/cache
                              │                    │ (SSE contract chốt ở T20)
            T22 web chat ◀─────────────────────────┘ ─▶ T23 citation panel ─▶ T24 history/a11y/E2E
                              │
            T25 containers + compose.prod ─▶ T26 observability/backup ─▶ T27 README + load test + eval GPU
```

## Task List (chi tiết trong `tasks/todo.md`)

### Phase 0: Nền móng
- [x] T1: Repo skeleton, tooling, infra dev (Postgres/Qdrant/Redis)

### Phase 1: Parse văn bản (rủi ro cao nhất)
- [x] T2: Đọc DOCX, chuẩn hóa, metadata
- [x] T3: Parser cấu trúc + kiểm tra toàn vẹn + `lawqa ingest --dry-run`
- [x] T4: Chunker theo cấu trúc

**Checkpoint 1** — dry-run trên file thật đúng 14 Chương / 212 Điều; người duyệt báo cáo parse.

### Phase 2: Lưu trữ & index
- [ ] T5: Model-server (embed + rerank)
- [ ] T6: DB schema + ghi văn bản/provision/chunk vào Postgres
- [ ] T7: BM25 tokenizer + encoder
- [ ] T8: Qdrant indexer + `lawqa ingest` / `reindex` / `documents`

**Checkpoint 2** — file 2013 nằm trong Postgres + Qdrant, số lượng khớp, nạp lại không trùng.

### Phase 3: Walking skeleton (CLI)
- [ ] T9: Hybrid retrieval + `lawqa search`
- [ ] T10: LLM client + kiểm tra trích dẫn
- [ ] T11: `HybridRAGPipeline` + context packing + `lawqa ask`

**Checkpoint 3** — `lawqa ask` trả lời có trích dẫn end-to-end trên Mac.

### Phase 4: Eval
- [ ] T12: Dataset + metric retrieval + ablation
- [ ] T13: Metric generation (LLM judge) + `eval-compare`

### Phase 5: Chất lượng
- [ ] T14: Rerank + từ chối khi không đủ căn cứ
- [ ] T15: Tra thẳng Điều/Khoản/Điểm được trích dẫn
- [ ] T16: Từ điển đồng nghĩa + truy vấn đa câu
- [ ] T17: Query understanding (intent, legal_query, missing_facts)
- [ ] T18: Prompt theo intent

**Checkpoint 4** — báo cáo baseline: `hybrid+rerank` > `dense-only`, `bm25-only`; query understanding cải thiện nhóm `layperson`.

### Phase 6: API
- [ ] T19: App factory, health, `/documents`, `/chunks/{id}`
- [ ] T20: `/ask` SSE + log truy vấn + feedback
- [ ] T21: Rate limit + giới hạn đồng thời + cache

**Checkpoint 5** — gọi `/ask` bằng curl thấy stream đúng contract; quá tải trả `BUSY`.

### Phase 7: Web
- [ ] T22: Next.js scaffold + trang hỏi đáp streaming
- [ ] T23: Panel nguyên văn, bố cục câu tình huống, feedback
- [ ] T24: Lịch sử local, footer, a11y, E2E

**Checkpoint 6** — luồng đầy đủ trên trình duyệt (desktop + mobile) ở môi trường dev.

### Phase 8: Production
- [ ] T25: Dockerfile + `compose.prod.yml` + Caddy + vLLM + `ops`
- [ ] T26: Metrics, dọn log, backup
- [ ] T27: README dev ≤ 30 phút, load test 20 người, eval chính thức trên GPU

**Checkpoint 7 (hoàn thành)** — mọi Success Criteria trong SPEC mục 10.

## Parallelization

- Song song được: T5 với T2–T4; T10 với T9; T12 bắt đầu viết dataset trong lúc làm T9–T11; T22 làm được với mock SSE ngay khi T20 chốt contract.
- Tuần tự bắt buộc: migration DB (T6 → T20), chuỗi ingest (T2 → T4 → T8).

## Risks and Mitigations

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| File DOCX có định dạng bất thường (Điều dính dòng, khoản xuống dòng giữa chừng, bảng) làm parse sai | Cao | Làm đầu tiên (T2–T3); kiểm tra toàn vẹn (liên tục 1..212, khớp ký tự); acceptance test trên file thật; báo cáo dry-run cho người duyệt |
| RAM 16GB trên M1 không đủ cho Qwen3-8B + BGE-M3 + reranker + Docker | Trung bình | fp16 cho model-server, nạp reranker lười; fallback `qwen3:4b`; đo ở Checkpoint 3 |
| FlagEmbedding/PyTorch trên MPS lỗi op | Trung bình | Model-server có `DEVICE=auto` → fallback CPU; test `/embed` ngay T5 |
| Tắt thinking mode của Qwen3 qua Ollama OpenAI-compatible API không như kỳ vọng | Trung bình | Kiểm chứng ở T10; fallback soft switch `/no_think` trong prompt + bỏ khối `<think>` khi stream |
| LLM 8B lượng tử hóa trả JSON sai schema (T17) | Trung bình | Structured output (`response_format` json_schema / Ollama `format`); validate Pydantic; fallback an toàn đã có trong spec |
| Qdrant thiếu tính năng (sparse IDF, Query API fusion, filter ngày) ở version cũ | Thấp | Pin image Qdrant ≥ 1.12 trong T1; integration test T8–T9 |
| Chưa có golden set / judge model | Trung bình | Seed set tự soạn + người duyệt (T12); endpoint judge cấu hình được (T13) |
| Tiếng Việt: lẫn NFC/NFD giữa dữ liệu và câu hỏi | Trung bình | Chuẩn hóa NFC ở cả ingest và query; unit test với chuỗi NFD |
| Chưa có máy GPU để kiểm Phase 8 | Trung bình | T25–T26 kiểm được bằng `docker compose config` + chạy CPU profile; T27 cần máy GPU thật |

## Open Questions (ảnh hưởng plan)

1. **Git:** thư mục chưa phải git repo. T1 sẽ `git init`, commit `SPEC.md` + `tasks/` lên `main`, rồi tạo `approach/hybrid-rag`. Mỗi task kết thúc bằng một commit — bạn có đồng ý để tôi tự commit sau mỗi task không?
2. **`raw_data/`:** commit vào git (đề xuất) hay gitignore? Acceptance test cần file này.
3. **Golden set:** định dạng/số câu? Nếu chưa có, T12 dùng seed set ~30 câu do tôi soạn từ Luật 2013, bạn duyệt.
4. **Judge cho eval (T13):** model local hay API ngoài?
5. **Máy GPU** cho T27: loại GPU/VRAM, có quyền truy cập khi tới Phase 8 không?
