# Task List: Law QA — Branch 1 (Hybrid RAG)

Plan: [`tasks/plan.md`](plan.md) · Spec: [`SPEC.md`](../SPEC.md)

Quy ước verify chung (Definition of Done cho mọi task): `make lint typecheck test` pass; không giảm coverage; không skip test; commit Conventional Commits.

---

## Phase 0: Nền móng

### - [x] T1: Repo skeleton, tooling, infra dev

**Description:** Khởi tạo git (`main` chứa SPEC + tasks, rồi branch `approach/hybrid-rag`), cấu trúc monorepo, `backend/` với uv + ruff + mypy + pytest, config qua pydantic-settings, CLI `lawqa` rỗng (typer), `compose.dev.yml` (Postgres 16, Qdrant ≥ 1.12 pin version, Redis 7) có healthcheck, Makefile với các target trong SPEC mục 5, `.env.example`, `.gitignore`.

**Acceptance criteria:**
- [ ] `make infra-up` → 3 container healthy; `make infra-down` dọn sạch
- [ ] `cd backend && uv run lawqa --help` chạy được; `Settings` đọc từ `.env`, thiếu biến bắt buộc → lỗi rõ ràng
- [ ] `make lint typecheck test` pass (có 1 test cho config)

**Verification:** `make infra-up && docker compose -f compose.dev.yml ps`; `make lint typecheck test`

**Dependencies:** None

**Files likely touched:** `Makefile`, `compose.dev.yml`, `.env.example`, `.gitignore`, `backend/pyproject.toml`, `backend/src/lawqa/{cli.py,core/config.py}`, `backend/tests/unit/test_config.py`

**Estimated scope:** M (nhiều file cấu hình nhỏ)

---

## Phase 1: Parse văn bản

### - [x] T2: Đọc DOCX, chuẩn hóa, metadata

**Description:** `docx_reader` trả danh sách đoạn (kể cả trong bảng) đúng thứ tự; `normalize` NFC, gộp khoảng trắng, tách phần đầu (quốc hiệu, số hiệu, tên) và phần cuối (thông qua ngày…, chữ ký); `metadata` trích số hiệu, loại, tên, ngày thông qua, ngày hiệu lực (từ Điều "Hiệu lực thi hành").

**Acceptance criteria:**
- [ ] Trên file 2013: `so_hieu=45/2013/QH13`, loại `Luật`, tên `Đất đai`, hiệu lực `2014-07-01`
- [ ] Chuỗi NFD đầu vào → NFC đầu ra; dòng "CỘNG HÒA XÃ HỘI…" và khối chữ ký không lọt vào thân văn bản
- [ ] Unit test dùng trích đoạn thật làm fixture (cả style `NormalWeb` lẫn không style)

**Verification:** `uv run pytest tests/unit/ingestion -q`

**Dependencies:** T1

**Files likely touched:** `backend/src/lawqa/ingestion/{docx_reader.py,normalize.py,metadata.py}`, `backend/tests/unit/ingestion/test_{docx_reader,normalize,metadata}.py`, `backend/tests/fixtures/`

**Estimated scope:** M

### - [x] T3: Parser cấu trúc + kiểm tra toàn vẹn + dry-run

**Description:** State machine dựa trên text: Chương (Ả Rập/La Mã + dòng tên), Mục, Điều, Khoản, Điểm (bảng chữ cái tiếng Việt có `đ`), đoạn không đánh số gắn đơn vị cha → cây `Provision` (Pydantic). `integrity` kiểm Điều liên tục, không trùng, tổng ký tự khớp. `lawqa ingest <file> --dry-run` in báo cáo (chưa ghi DB).

**Acceptance criteria:**
- [ ] File 2013: 14 Chương, 212 Điều liên tục; Điều 100 có đúng số Khoản/Điểm như văn bản
- [ ] Ghép text từ cây provision = text thân văn bản sau chuẩn hóa (acceptance test, marker `corpus`)
- [ ] Văn bản lỗi (thiếu Điều, Điều trùng) → dry-run báo lỗi kèm vị trí, exit code ≠ 0

**Verification:** `uv run pytest -m corpus tests/acceptance -q`; `uv run lawqa ingest ../raw_data/Luật-45-2013-QH13.docx --dry-run`

**Dependencies:** T2

**Files likely touched:** `backend/src/lawqa/ingestion/{legal_parser.py,integrity.py,models.py}`, `backend/src/lawqa/cli.py`, `backend/tests/unit/ingestion/test_legal_parser.py`, `backend/tests/acceptance/test_luat_2013.py`

**Estimated scope:** M

### - [x] T4: Chunker theo cấu trúc

**Description:** Chunk = 1 Điều; Điều > `CHUNK_MAX_TOKENS` → tách theo Khoản (gộp Khoản ngắn liền nhau), Khoản quá dài → theo Điểm. `context_text` = breadcrumb + nội dung; `text` = nguyên văn. Đếm token bằng tokenizer BGE-M3 (`tokenizers`). Dry-run in phân bố độ dài chunk.

**Acceptance criteria:**
- [ ] Mọi chunk của file 2013 có `context_text` ≤ 512 token
- [ ] Không mất/không lặp nội dung: hợp các `text` của chunk thuộc một Điều = text Điều
- [ ] Mỗi chunk có `path` ổn định (chạy lại cho cùng kết quả)

**Verification:** `uv run pytest tests/unit/ingestion/test_chunker.py tests/acceptance -q`

**Dependencies:** T3

**Files likely touched:** `backend/src/lawqa/ingestion/{chunker.py,tokens.py}`, `backend/src/lawqa/cli.py`, `backend/tests/unit/ingestion/test_chunker.py`, `backend/tests/acceptance/test_luat_2013.py`

**Estimated scope:** S

### Checkpoint 1: Parse
- [x] `make lint typecheck test` + acceptance pass
- [x] Dry-run trên file 2013 đúng 14 Chương / 212 Điều, mọi chunk ≤ 512 token
- [x] **Người duyệt** báo cáo dry-run + mẫu 3 Điều (ngắn, trung bình, dài nhất) trước khi đi tiếp
- [x] Kết quả duyệt: sửa lỗi đánh máy điểm g) → e) ở Điều 40 khoản 4 trong file gốc; chuyên gia xác nhận đoạn không đánh số thuộc đơn vị đứng trước nó (khóa bằng acceptance test); sửa bộ đọc DOCX làm mất chữ trong smart tag ("Việt Nam")

---

## Phase 2: Lưu trữ & index

### - [x] T5: Model-server (embed + rerank)

**Description:** Service FastAPI riêng: `POST /embed` (dense BGE-M3, batch, normalize), `POST /rerank` (bge-reranker-v2-m3), `GET /healthz`; `DEVICE=auto` (cuda → mps → cpu), fp16 khi có GPU, reranker nạp lười. `make models` tải weights, `make dev-models` chạy native.

**Acceptance criteria:**
- [ ] Trên Mac: `/healthz` báo `device=mps`; embed 32 câu tiếng Việt trả vector 1024 chiều, chuẩn hóa L2
- [ ] `/rerank` xếp đoạn liên quan cao hơn đoạn không liên quan (test với 1 cặp tiếng Việt rõ ràng)
- [ ] Input rỗng/quá dài → 422 rõ ràng; test đơn vị chạy không cần tải model (fake backend), test thật đánh marker `models`

**Verification:** `cd model-server && uv run pytest -q`; `make dev-models` + `curl localhost:8001/healthz`

**Dependencies:** T1 (song song T2–T4)

**Files likely touched:** `model-server/pyproject.toml`, `model-server/src/model_server/{main.py,models.py,schemas.py}`, `model-server/tests/test_api.py`

**Estimated scope:** M

### - [x] T6: DB schema + ghi Postgres

**Description:** SQLAlchemy models + Alembic migration đầu tiên: `documents`, `provisions`, `chunks`, `corpus_state` (có `valid_from`/`valid_to`). Repository ghi một văn bản trong một transaction; idempotent theo `sha256`; `--replace` xóa và nạp lại; `corpus_version` tăng mỗi lần thay đổi.

**Acceptance criteria:**
- [ ] `make migrate` tạo schema trên DB rỗng; downgrade chạy được
- [ ] Ghi file 2013: 212 Điều trong `provisions`, số chunk khớp dry-run; ghi lại cùng file → không đổi gì, `corpus_version` giữ nguyên
- [ ] Lỗi giữa chừng → rollback toàn bộ (integration test)

**Verification:** `uv run pytest tests/integration/test_store.py -q` (testcontainers Postgres)

**Dependencies:** T4

**Files likely touched:** `backend/src/lawqa/db/{models.py,session.py}`, `backend/alembic/versions/0001_corpus.py`, `backend/src/lawqa/ingestion/store.py`, `backend/tests/integration/test_store.py`

**Estimated scope:** M

### - [x] T7: BM25 tokenizer + encoder

**Description:** Tokenizer: NFC, lowercase, âm tiết + bigram âm tiết, giữ định danh pháp lý (`45/2013/qh13`, `điều 100`, `khoản 2`) thành một token. Encoder: TF bão hòa BM25 (`k1`, `b`, `avgdl` lưu theo collection) → sparse vector `{indices: mmh3, values}`.

**Acceptance criteria:**
- [ ] "Người lao động" và "người  lao   động" (NFD) cho cùng tokens
- [ ] "45/2013/QH13" là một token; "Điều 100" sinh token định danh `điều 100`
- [ ] Encode thuần hàm, deterministic, không I/O

**Verification:** `uv run pytest tests/unit/retrieval/test_bm25.py -q`

**Dependencies:** T1

**Files likely touched:** `backend/src/lawqa/retrieval/bm25_tokenizer.py`, `backend/src/lawqa/retrieval/bm25.py`, `backend/tests/unit/retrieval/test_bm25.py`

**Estimated scope:** S

### - [x] T8: Qdrant indexer + CLI nạp thật

**Description:** Tạo collection (named vectors `dense` 1024 cosine + sparse `bm25` với `modifier: idf`, payload index `so_hieu`, `dieu`, `valid_from`, `valid_to`). `lawqa ingest` = parse → chunk → Postgres → embed qua model-server (batch) → upsert Qdrant (id `uuid5`). `lawqa reindex` rebuild từ Postgres. `lawqa documents list|show|remove`.

**Acceptance criteria:**
- [ ] Sau `make ingest FILE=raw_data/Luật-45-2013-QH13.docx`: số point Qdrant = số chunk Postgres
- [ ] `lawqa reindex` trên collection trống cho cùng số point và cùng id
- [ ] `documents remove 45/2013/QH13` xóa sạch ở cả 2 nơi; model-server không chạy → lỗi rõ ràng, Postgres không bị ghi dở

**Verification:** `uv run pytest tests/integration/test_indexer.py -q` (Qdrant testcontainer + fake encoder); chạy thật trên Mac

**Dependencies:** T5, T6, T7

**Files likely touched:** `backend/src/lawqa/ingestion/indexer.py`, `backend/src/lawqa/retrieval/encoder_client.py`, `backend/src/lawqa/cli.py`, `backend/tests/integration/test_indexer.py`

**Estimated scope:** M

### Checkpoint 2: Dữ liệu đã nạp
- [x] Tests pass; Luật 2013 nằm trong Postgres + Qdrant, số lượng khớp (279 chunk / 279 point; 212 Điều, 782 khoản, 609 điểm)
- [x] Nạp lại không trùng (unchanged, 2.5s); reindex tái tạo đúng 279 point cùng id; model-server tắt → lỗi rõ, index không bị xóa

---

## Phase 3: Walking skeleton (CLI)

### - [x] T9: Hybrid retrieval + `lawqa search`

**Description:** `HybridRetriever.search(texts, reference_date)`: prefetch dense + bm25 cho mỗi câu, fusion RRF, filter `valid_at`. Chế độ `dense-only` / `bm25-only` / `hybrid` qua config (phục vụ ablation). `lawqa search "<q>" [--mode]` in top-k với điểm.

**Acceptance criteria:**
- [ ] "cấp giấy chứng nhận quyền sử dụng đất cho hộ gia đình" → Điều 100 hoặc 101 trong top-5 (chạy thật)
- [ ] Filter `valid_at` loại chunk có `valid_to` ≤ ngày truy vấn (integration test với dữ liệu giả)
- [ ] 3 chế độ trả kết quả khác nhau và đều được log tham số

**Verification:** `uv run pytest tests/integration/test_hybrid.py -q`; `uv run lawqa search "..."`

**Dependencies:** T8

**Files likely touched:** `backend/src/lawqa/retrieval/{hybrid.py,filters.py,types.py}`, `backend/src/lawqa/cli.py`, `backend/tests/integration/test_hybrid.py`

**Estimated scope:** M

### - [x] T10: LLM client + kiểm tra trích dẫn

**Description:** Client OpenAI-compatible (`LLM_BASE_URL`, `LLM_MODEL`), streaming, timeout + retry backoff, tắt thinking của Qwen3 (kiểm chứng trên Ollama; fallback `/no_think` + lọc `<think>`). `citations.py`: tìm `[n]`, loại `[n]` không có trong nguồn, trả danh sách trích dẫn hợp lệ + số bị loại.

**Acceptance criteria:**
- [ ] Gọi thật Ollama `qwen3:8b`: stream ra token, không có nội dung `<think>`
- [ ] Lỗi mạng/timeout → exception nghiệp vụ rõ ràng sau N lần retry
- [ ] Văn bản có `[1][7]` với 3 nguồn → giữ `[1]`, loại `[7]`, `invalid=1`

**Verification:** `uv run pytest tests/unit/generation -q`; smoke `uv run python -m lawqa.generation.llm_client` (marker `llm`, không chạy trong CI)

**Dependencies:** T1 (song song T9)

**Files likely touched:** `backend/src/lawqa/generation/{llm_client.py,citations.py}`, `backend/tests/unit/generation/test_{llm_client,citations}.py`

**Estimated scope:** S

### - [x] T11: `HybridRAGPipeline` + context packing + `lawqa ask`

**Description:** `RAGPipeline` Protocol + `PipelineEvent` (meta/sources/token/done/error). `HybridRAGPipeline`: retrieve → `context_packer` (gom theo Điều, sắp theo thứ tự, ≤ `CONTEXT_MAX_TOKENS`) → prompt chung (chỉ dùng nguồn, trích `[n]`, miễn trừ) → stream → kiểm tra trích dẫn. `lawqa ask "<q>"` in stream + nguồn.

**Acceptance criteria:**
- [ ] `lawqa ask "Điều kiện chuyển nhượng quyền sử dụng đất là gì?"` trả lời tiếng Việt có ≥ 1 trích dẫn hợp lệ trỏ tới Điều liên quan (chạy thật trên Mac)
- [ ] Pipeline test với fake retriever + fake LLM: thứ tự event đúng contract SSE trong SPEC 3.6
- [ ] Context không vượt `CONTEXT_MAX_TOKENS`

**Verification:** `uv run pytest tests/unit/pipelines -q`; chạy `lawqa ask` thật

**Dependencies:** T9, T10

**Files likely touched:** `backend/src/lawqa/pipelines/{base.py,hybrid.py}`, `backend/src/lawqa/retrieval/context_packer.py`, `backend/src/lawqa/generation/prompts/base.jinja`, `backend/tests/unit/pipelines/test_hybrid.py`

**Estimated scope:** M

### Checkpoint 3: Walking skeleton
- [x] Tests pass; `lawqa ask` chạy end-to-end trên Mac
- [x] Ghi lại RAM đỉnh & latency một câu hỏi trên M1 (quyết định giữ `qwen3:8b` hay chuyển `qwen3:4b`)
- [x] **Người duyệt** thử ~10 câu hỏi (cả kiểu người dân lẫn chuyên môn)
- [x] Kết quả: dev dùng `qwen3:4b-instruct` (không dùng tag `qwen3:4b` = bản Thinking). 10 câu: 4b 6✅/2⚠️/2❌, ~28s/câu; 8b 5✅/2⚠️/3❌, ~66s/câu, swap nhiều trên M1 16GB. Lỗi còn lại giao cho T14 (rerank), T15 ("Điều 100" không tìm ra), T16 ("thổ cư"→"đất ở"), T17 (ngoài phạm vi vẫn gọi LLM), T18 (gán nhầm nguồn)

---

## Phase 4: Eval

### - [x] T12: Dataset + metric retrieval + ablation

> **Baseline (seed.jsonl, 29 câu có đáp án, Luật 45/2013, commit 3162cce):**
> | chế độ | R@5 | R@10 | MRR@10 | nDCG@10 |
> |---|---|---|---|---|
> | dense | 0.816 | 0.885 | 0.747 | 0.760 |
> | bm25 | 0.690 | 0.845 | 0.592 | 0.635 |
> | hybrid | 0.822 | 0.833 | 0.740 | 0.752 |
> Hybrid chưa vượt dense: lookup ("Điều 100…") = 0 ở dense/hybrid (→ T15); BM25 yếu với câu người dân (R@10 0.70) kéo hybrid xuống ở nhóm layperson (→ T14, T16, T17). Ngưỡng hồi quy tạm: `make eval ARGS="--min-recall 0.80"`.

**Description:** Định dạng `golden.jsonl` theo SPEC 3.8 + script convert từ golden set của bạn (khi có). Trước mắt: `seed.jsonl` ~30 câu (chia đều persona/intent) tôi soạn từ Luật 2013, **người duyệt**. Runner: Recall@5/10, MRR@10, nDCG@10 theo `dieu[/khoan]`, chạy các chế độ ablation, xuất JSON + Markdown có git SHA + config hash. Cũng dùng làm retrieval regression test.

**Acceptance criteria:**
- [ ] `make eval SET=eval/datasets/seed.jsonl MODE=retrieval` sinh `eval/results/*.json` + `report.md` có bảng 3 chế độ, chia theo persona/intent
- [ ] Metric đúng trên ví dụ tính tay (unit test)
- [ ] Regression test: Recall@10 (hybrid) ≥ ngưỡng chốt sau lần chạy đầu

**Verification:** `uv run pytest tests/unit/eval -q`; `make eval ...`

**Dependencies:** T11

**Files likely touched:** `backend/src/lawqa/eval/{dataset.py,metrics/retrieval.py,runner.py,report.py}`, `eval/datasets/seed.jsonl`

**Estimated scope:** M

### - [x] T13: Metric generation + `eval-compare`

**Description:** LLM judge qua endpoint cấu hình riêng (`JUDGE_BASE_URL`, `JUDGE_MODEL`), prompt chấm faithfulness, correctness, độ dễ hiểu (layperson); citation precision/recall tính bằng code; refusal đúng/sai; latency từng giai đoạn. `make eval-compare` gộp nhiều file kết quả thành một bảng.

**Acceptance criteria:**
- [ ] Judge trả JSON hợp lệ hoặc được đánh dấu lỗi (không làm hỏng cả lần chạy)
- [ ] Báo cáo có đủ metric SPEC 3.8; `eval-compare` so sánh ≥ 2 lần chạy
- [ ] Judge không bao giờ dùng chung endpoint với model đang được đánh giá trừ khi cấu hình rõ ràng

**Verification:** `uv run pytest tests/unit/eval -q`; `make eval SET=... MODE=full`

**Dependencies:** T12

**Files likely touched:** `backend/src/lawqa/eval/{judge.py,metrics/generation.py,compare.py}`, `backend/tests/unit/eval/test_generation_metrics.py`

**Estimated scope:** M

---

## Phase 5: Chất lượng

### - [x] T14: Rerank + từ chối khi không đủ căn cứ

> **Kết quả (seed, 40 ứng viên):** hybrid+rerank R@5 0.851 · R@10 0.902 · MRR 0.845 · nDCG 0.839 (hybrid: 0.822/0.833/0.740/0.752). Ngưỡng `RERANK_MIN_SCORE=0.005` (ngoài phạm vi 0.0009–0.0073, câu hợp lệ thấp nhất 0.0062). Trên M1 rerank ~1s/đoạn → 36–60s/câu với 40 ứng viên; giảm `RERANK_CANDIDATES` khi dev nếu cần.

**Description:** Client `/rerank`; rerank top-40 → top-8; điểm cao nhất < `RERANK_MIN_SCORE` → event "không đủ căn cứ" (không gọi LLM). Thêm chế độ ablation `hybrid+rerank`.

**Acceptance criteria:**
- [ ] Eval: `hybrid+rerank` ≥ `hybrid` về nDCG@10 trên seed set (ghi số vào report)
- [ ] Câu hỏi ngoài dữ liệu (vd giao thông) → từ chối, không gọi LLM sinh (test với fake)
- [ ] Ngưỡng nằm trong config, được log

**Verification:** `uv run pytest tests/unit/retrieval/test_rerank.py tests/unit/pipelines -q`; `make eval`

**Dependencies:** T13

**Files likely touched:** `backend/src/lawqa/retrieval/rerank.py`, `backend/src/lawqa/pipelines/hybrid.py`, `backend/tests/unit/retrieval/test_rerank.py`

**Estimated scope:** S

### - [x] T15: Tra thẳng Điều/Khoản/Điểm được trích dẫn

**Description:** Regex nhận "Điều 100", "khoản 2 Điều 5", "điểm a khoản 1 Điều 100" (có/không dấu, hoa/thường) → lấy chunk tương ứng từ Postgres, chèn đầu danh sách trước rerank.

**Acceptance criteria:**
- [ ] "Điều 100 quy định gì?" → nguồn [1] là Điều 100 (100% trên mọi Điều 1..212 trong test tham số hóa)
- [ ] "điểm đ khoản 1 Điều 100" trỏ đúng điểm `đ`
- [ ] Câu không có trích dẫn → không ảnh hưởng kết quả

**Verification:** `uv run pytest tests/unit/understanding/test_citation_regex.py tests/integration/test_citation_lookup.py -q`

**Dependencies:** T14

**Files likely touched:** `backend/src/lawqa/understanding/citation_regex.py`, `backend/src/lawqa/retrieval/citation_lookup.py`, `backend/src/lawqa/pipelines/hybrid.py`, tests

**Estimated scope:** S

### - [ ] T16: Từ điển đồng nghĩa + truy vấn đa câu

**Description:** `resources/dat_dai_synonyms.yaml` (bản đầu ~50 mục, **người duyệt**); mở rộng truy vấn BM25 bằng luật; retrieval nhận nhiều câu (gốc + mở rộng) gộp RRF.

**Acceptance criteria:**
- [ ] "sổ đỏ" mở rộng thành "giấy chứng nhận quyền sử dụng đất"; từ điển được validate khi load
- [ ] Eval nhóm `layperson`: Recall@10 không giảm, ghi số vào report
- [ ] Tắt được bằng config

**Verification:** `uv run pytest tests/unit/understanding/test_synonyms.py -q`; `make eval`

**Dependencies:** T14

**Files likely touched:** `backend/resources/dat_dai_synonyms.yaml`, `backend/src/lawqa/understanding/synonyms.py`, `backend/src/lawqa/retrieval/hybrid.py`, tests

**Estimated scope:** S

### - [ ] T17: Query understanding

**Description:** Một lần gọi LLM với structured output → `intent`, `legal_query`, `citations`, `missing_facts`; validate Pydantic; timeout/JSON lỗi → fallback `topic_search` + câu gốc; `out_of_scope` → câu từ chối cố định, bỏ qua retrieval. Retrieval dùng câu gốc + `legal_query` + mở rộng đồng nghĩa. Thêm chế độ ablation.

**Acceptance criteria:**
- [ ] 20 câu mẫu có nhãn intent: phân loại đúng ≥ 85% (chạy thật, ghi kết quả)
- [ ] JSON lỗi/timeout → fallback, câu trả lời vẫn sinh (test với fake LLM)
- [ ] Eval: Recall@10 nhóm `layperson` tăng so với không có understanding

**Verification:** `uv run pytest tests/unit/understanding -q`; `make eval`

**Dependencies:** T15, T16

**Files likely touched:** `backend/src/lawqa/understanding/{classifier.py,schemas.py,prompts/understand.jinja}`, `backend/src/lawqa/pipelines/hybrid.py`, `backend/tests/unit/understanding/test_classifier.py`

**Estimated scope:** M

### - [ ] T18: Prompt theo intent

**Description:** Template `situation` (Kết luận → giải thích theo điều kiện → thông tin nên bổ sung → căn cứ; mức phạt không có trong dữ liệu thì nói rõ), `lookup`, `topic_search`, `procedure`; miễn trừ trách nhiệm chung; `done` event mang `missing_facts`.

**Acceptance criteria:**
- [ ] Câu `situation` luôn có phần "Kết luận" và "Căn cứ pháp lý" (kiểm tra cấu trúc trên seed set)
- [ ] Câu `lookup` chứa nguyên văn Điều được hỏi
- [ ] Eval full: faithfulness và citation precision không giảm so với prompt chung

**Verification:** `uv run pytest tests/unit/generation/test_prompts.py -q`; `make eval MODE=full`

**Dependencies:** T17

**Files likely touched:** `backend/src/lawqa/generation/prompts/{situation,lookup,topic_search,procedure}.jinja`, `backend/src/lawqa/generation/prompt_builder.py`, `backend/tests/unit/generation/test_prompts.py`

**Estimated scope:** S

### Checkpoint 4: Baseline chất lượng
- [ ] Tests pass; báo cáo eval đầy đủ 5 chế độ ablation được lưu trong `eval/results/`
- [ ] `hybrid+rerank` > `dense-only` và `bm25-only`; understanding cải thiện `layperson`
- [ ] **Người duyệt** báo cáo và chốt ngưỡng Recall@10

---

## Phase 6: API

### - [ ] T19: App factory, health, endpoint đọc

**Description:** FastAPI app factory, DI cho pipeline/repo/clients, structlog JSON với `request_id`, error mapping một chỗ; `/healthz`, `/readyz` (DB, Qdrant, Redis, LLM, model-server), `GET /documents`, `GET /chunks/{id}`.

**Acceptance criteria:**
- [ ] `/readyz` trả 503 kèm thành phần lỗi khi tắt Qdrant
- [ ] `/chunks/{id}` trả nguyên văn + vị trí Chương/Điều/Khoản; id không tồn tại → 404
- [ ] Mọi log request có `request_id`

**Verification:** `uv run pytest tests/integration/api/test_read.py -q`; `make dev-api` + curl

**Dependencies:** T11

**Files likely touched:** `backend/src/lawqa/main.py`, `backend/src/lawqa/api/{deps.py,routers/health.py,routers/corpus.py}`, `backend/tests/integration/api/test_read.py`

**Estimated scope:** M

### - [ ] T20: `/ask` SSE + log truy vấn + feedback

**Description:** `POST /ask` stream SSE đúng contract SPEC 3.6; migration bảng `queries` + `feedback`; ghi log sau khi stream xong (câu hỏi, intent, chunk ids + điểm, câu trả lời, latency từng giai đoạn, git SHA, `ip_hash` HMAC); `POST /queries/{id}/feedback`; câu hỏi > 1.000 ký tự → 422; client ngắt kết nối → hủy sinh.

**Acceptance criteria:**
- [ ] `curl -N` thấy đủ `meta → sources → token… → done`; lỗi LLM → `error` rồi đóng
- [ ] Bảng `queries` có đủ trường, không có IP thô
- [ ] Feedback cho `query_id` không tồn tại → 404

**Verification:** `uv run pytest tests/integration/api/test_ask.py -q`

**Dependencies:** T18, T19

**Files likely touched:** `backend/src/lawqa/api/{routers/ask.py,sse.py,routers/feedback.py}`, `backend/alembic/versions/0002_queries.py`, `backend/tests/integration/api/test_ask.py`

**Estimated scope:** M

### - [ ] T21: Rate limit + giới hạn đồng thời + cache

**Description:** Rate limit theo IP trên Redis (10/phút, 100/ngày, cấu hình được) → 429; semaphore `MAX_CONCURRENT_GENERATIONS` + chờ tối đa 30s → `BUSY`; cache câu trả lời (khóa gồm câu chuẩn hóa + pipeline + config hash + `corpus_version`), phát lại dạng SSE với `cached=true`.

**Acceptance criteria:**
- [ ] Request thứ 11 trong 1 phút → 429 có `Retry-After`
- [ ] Vượt giới hạn đồng thời (test với fake LLM chậm) → `BUSY`, không treo
- [ ] Hỏi lại cùng câu → `cached=true`; `ingest --replace` → cache cũ không còn được dùng

**Verification:** `uv run pytest tests/integration/api/test_protection.py -q`

**Dependencies:** T20

**Files likely touched:** `backend/src/lawqa/core/{rate_limit.py,cache.py}`, `backend/src/lawqa/api/concurrency.py`, `backend/src/lawqa/api/routers/ask.py`, `backend/tests/integration/api/test_protection.py`

**Estimated scope:** M

### Checkpoint 5: API
- [ ] Tests pass; `/ask` qua curl đúng contract trên Mac
- [ ] Rate limit, BUSY, cache hoạt động

---

## Phase 7: Web

### - [ ] T22: Next.js scaffold + trang hỏi đáp streaming

**Description:** Next.js (App Router, TS strict, Tailwind, shadcn/ui, pnpm); API client duy nhất trong `src/lib`; parser SSE (POST + stream) có test; trang `/`: ô nhập, câu gợi ý, render câu trả lời streaming (markdown an toàn) + danh sách nguồn; xử lý `BUSY`/429/lỗi mạng.

**Acceptance criteria:**
- [ ] Gõ câu hỏi → chữ hiện dần, nguồn hiện khi có event `sources`
- [ ] Parser SSE xử lý event bị cắt ngang giữa 2 chunk mạng (Vitest)
- [ ] `pnpm lint typecheck test build` pass

**Verification:** `pnpm -C web test && pnpm -C web build`; `make dev-web` thử thật

**Dependencies:** T20 (T21 không bắt buộc)

**Files likely touched:** `web/package.json`, `web/src/app/page.tsx`, `web/src/lib/{api.ts,sse.ts}`, `web/src/components/Answer.tsx`, `web/tests/sse.test.ts`

**Estimated scope:** M

### - [ ] T23: Panel nguyên văn, bố cục câu tình huống, feedback

**Description:** Bấm `[n]` → panel/drawer gọi `/chunks/{id}` hiển thị nguyên văn + vị trí; câu `situation` hiển thị khối "Kết luận" nổi bật và "Thông tin nên bổ sung" (từ `missing_facts`); nút 👍/👎 + ghi chú.

**Acceptance criteria:**
- [ ] Bấm trích dẫn mở đúng Điều/Khoản, đóng được bằng Esc
- [ ] Câu tình huống hiển thị 2 khối riêng; câu tra cứu không hiển thị khối thừa
- [ ] Gửi feedback thành công/thất bại có phản hồi rõ

**Verification:** `pnpm -C web test`; thử thật

**Dependencies:** T22

**Files likely touched:** `web/src/components/{CitationPanel.tsx,SituationAnswer.tsx,Feedback.tsx}`, `web/src/lib/api.ts`, `web/tests/components.test.tsx`

**Estimated scope:** M

### - [ ] T24: Lịch sử local, footer, a11y, E2E

**Description:** Sidebar lịch sử `localStorage` (try/catch, xóa được); footer: văn bản đang áp dụng, miễn trừ, thông báo quyền riêng tư; responsive mobile; keyboard, contrast AA, `aria-live` vùng streaming; Playwright E2E với backend fake.

**Acceptance criteria:**
- [ ] Tải lại trang vẫn thấy lịch sử; localStorage bị chặn → trang vẫn chạy
- [ ] E2E: hỏi → stream + trích dẫn → mở nguyên văn; câu ngoài phạm vi bị từ chối; viewport 375px không cuộn ngang
- [ ] Không có lỗi axe mức serious/critical trên `/`

**Verification:** `pnpm -C web exec playwright test`

**Dependencies:** T23

**Files likely touched:** `web/src/components/{History.tsx,Footer.tsx}`, `web/src/lib/history.ts`, `web/e2e/ask.spec.ts`, `web/playwright.config.ts`

**Estimated scope:** M

### Checkpoint 6: Web
- [ ] Tests + E2E pass; luồng đầy đủ trên trình duyệt (desktop + mobile) ở dev
- [ ] **Người duyệt** giao diện

---

## Phase 8: Production

### - [ ] T25: Container + `compose.prod.yml`

**Description:** Dockerfile multi-stage cho api (+ target `ops` để chạy `lawqa`), model-server (CUDA base), web (standalone); `compose.prod.yml`: caddy (TLS, chặn `/metrics` từ ngoài, security headers), web, api (migration one-shot trước), model-server, vLLM (`Qwen/Qwen3-8B`, args trong `deploy/`), postgres, qdrant, redis — healthcheck, restart, resource limits, volume.

**Acceptance criteria:**
- [ ] `docker compose -f compose.prod.yml config` hợp lệ; các image build được
- [ ] Profile CPU (không vLLM, trỏ LLM sang Ollama) chạy được trên Mac để kiểm tra nối dây
- [ ] `make prod-ingest FILE=…` nạp được qua service `ops`

**Verification:** `docker compose -f compose.prod.yml build`; chạy profile CPU

**Dependencies:** T21, T24

**Files likely touched:** `backend/Dockerfile`, `model-server/Dockerfile`, `web/Dockerfile`, `compose.prod.yml`, `deploy/Caddyfile`

**Estimated scope:** M

### - [ ] T26: Metrics, dọn log, backup

**Description:** Prometheus metrics (latency từng stage, lỗi LLM, độ dài hàng đợi, rate-limit hits, cache hit rate); job dọn `queries` quá `LOG_RETENTION_DAYS`; `make backup` (`pg_dump` có xoay vòng) + hướng dẫn restore + `lawqa reindex`.

**Acceptance criteria:**
- [ ] `/metrics` có các series trên, không truy cập được qua Caddy từ ngoài
- [ ] Bản ghi cũ hơn retention bị xóa (integration test)
- [ ] Restore từ backup vào DB trống + reindex → hệ thống trả lời được

**Verification:** `uv run pytest tests/integration/test_retention.py -q`; diễn tập restore

**Dependencies:** T25

**Files likely touched:** `backend/src/lawqa/core/metrics.py`, `backend/src/lawqa/cli.py` (lệnh `cleanup`), `deploy/backup.sh`, `backend/tests/integration/test_retention.py`

**Estimated scope:** M

### - [ ] T27: README, load test, eval chính thức trên GPU

**Description:** README dev (máy sạch → câu hỏi đầu tiên ≤ 30 phút) + runbook prod; script load test async (httpx, không thêm dependency mới) 20 người dùng đồng thời; triển khai lên máy GPU, nạp Luật 2013, chạy eval chính thức → baseline cho branch 2/3.

**Acceptance criteria:**
- [ ] Một người làm theo README trên Mac sạch hỏi được câu đầu tiên ≤ 30 phút
- [ ] Load test 20 người: không lỗi 5xx; retrieval+rerank p95 ≤ 500ms; TTFT p95 ≤ 3s (trên GPU)
- [ ] Báo cáo eval chính thức lưu trong `eval/results/`, đạt Success Criteria SPEC mục 10

**Verification:** chạy load test + `make eval` trên máy GPU

**Dependencies:** T26 (cần truy cập máy GPU)

**Files likely touched:** `README.md`, `docs/runbook-prod.md`, `scripts/load_test.py`, `eval/results/`

**Estimated scope:** M

### Checkpoint 7: Hoàn thành Branch 1
- [ ] Mọi Success Criteria SPEC mục 10 đạt
- [ ] **Người duyệt** trước khi checkout `approach/hybrid-graph-rag`
