# Spec: Law QA — Hỏi đáp Luật Đất đai (Branch 1: Hybrid RAG)

> Trạng thái: **DRAFT v5 — chờ duyệt**
> v5: thu gọn phạm vi — giai đoạn này **chỉ nạp Luật Đất đai 2013 (45/2013/QH13)**. Cơ chế cập nhật văn bản (sửa đổi, thay thế, ưu tiên áp dụng) chuyển sang giai đoạn sau (mục 13); thiết kế dữ liệu hiện tại vẫn chừa sẵn chỗ cho nó.
> Branch 2 (Hybrid RAG + Graph) và Branch 3 (Agentic RAG) có spec riêng khi tới lượt.

---

## 1. Objective

### Bối cảnh
Xây dựng hệ thống hỏi đáp **Luật Đất đai Việt Nam** dùng LLM, **public, triển khai thực tế** (không phải demo). Ai cũng dùng được, không cần đăng nhập. Dự án đồng thời là nền tảng để **so sánh khách quan 3 phương pháp RAG** trên cùng dữ liệu, cùng bộ câu hỏi, cùng thước đo:

| Branch | Phương pháp | Thứ tự |
|---|---|---|
| `approach/hybrid-rag` | Hybrid RAG (dense + BM25 + rerank) | 1 — spec này |
| `approach/hybrid-graph-rag` | Hybrid RAG + Knowledge Graph | 2 — checkout từ branch 1 |
| `approach/agentic-rag` | Agentic RAG | 3 — checkout từ branch 2 |

### Dữ liệu giai đoạn này
Duy nhất `raw_data/Luật-45-2013-QH13.docx` — **Luật Đất đai số 45/2013/QH13**, được coi là luật hiện hành.
Đặc điểm đã kiểm tra trong file: 14 Chương (đánh số Ả Rập: `Chương 1.`), 212 Điều, không có Mục; Điều ngắn nhất ~40 từ, trung vị ~250 từ, dài nhất ~1.370 từ (56 Điều dài hơn ~380 từ → phải tách theo Khoản); điểm dùng chữ cái tiếng Việt (`a)`, `b)`, …, `đ)`, …); hiệu lực 01/07/2014 (Điều 211).

Các file còn lại trong `raw_data/` (31/2024, 43/2024, NQ 254/2025) **chưa nạp** ở giai đoạn này.

### Người dùng
Không phân loại người dùng theo tài khoản. Hệ thống **phân loại theo từng câu hỏi**, vì cùng một người có thể lúc hỏi kiểu chuyên môn, lúc hỏi kiểu đời thường.

| Kiểu câu hỏi | Ví dụ | Nhu cầu |
|---|---|---|
| **Tình huống / hành vi** (người dân) | "Tôi xây nhà trên đất ruộng nhà mình có bị phạt không?" | Biết mình có vi phạm không, bằng ngôn ngữ dễ hiểu; từ ngữ đời thường ("sổ đỏ", "đất thổ cư") |
| **Tra cứu điều khoản** (chuyên môn) | "Điều 100 Luật Đất đai quy định gì?" | Nguyên văn điều luật, chính xác |
| **Tìm quy định theo chủ đề** (chuyên môn) | "Điều kiện chuyển mục đích sử dụng đất nông nghiệp sang đất ở" | Các căn cứ pháp lý liên quan, kèm trích dẫn |
| **Thủ tục** | "Làm sổ đỏ lần đầu cần giấy tờ gì?" | Các bước, hồ sơ, cơ quan, có căn cứ |
| **Ngoài phạm vi** | "Vượt đèn đỏ phạt bao nhiêu?" | Từ chối lịch sự: hệ thống chỉ hỗ trợ lĩnh vực đất đai |

### User stories
- Mở web → trang chủ chính là khung hỏi đáp → gõ câu hỏi → nhận câu trả lời **streaming**, có **trích dẫn** (Điều, Khoản, Điểm), bấm trích dẫn xem **nguyên văn**.
- Câu hỏi tình huống thiếu dữ kiện → trả lời **theo điều kiện** ("Nếu đất của bạn là X thì…, nếu là Y thì…") và nêu thông tin nên bổ sung. Mỗi câu hỏi độc lập (không hội thoại nhiều lượt).
- Lịch sử câu hỏi lưu **trong trình duyệt** (không có tài khoản).
- Đánh giá câu trả lời 👍/👎 + ghi chú (ẩn danh).
- **Người vận hành** nạp văn bản bằng **CLI** sau khi hệ thống đã dựng xong.

### Ngoài phạm vi giai đoạn này
- Nạp Luật 31/2024, 43/2024, NQ 254/2025; mọi cơ chế sửa đổi/thay thế/ưu tiên áp dụng (xem mục 13).
- Đăng nhập, tài khoản, giao diện admin.
- Hội thoại nhiều lượt; crawl dữ liệu; OCR.

### Giả định (cần xác nhận)
1. "Hiện hành" = những gì có trong corpus. LLM **không được** dùng hiểu biết sẵn có về luật mới hơn (vd Luật Đất đai 2024) — prompt ràng buộc chỉ trả lời từ nguồn được cung cấp.
2. File 2013 là bản gốc, chưa hợp nhất các sửa đổi sau này (vd Luật 35/2018/QH14) — chấp nhận cho giai đoạn này.
3. Câu hỏi về **mức phạt cụ thể** được trả lời là "quy định tại nghị định xử phạt, hiện chưa có trong dữ liệu".
4. Tải: ≤ 20 người dùng đồng thời.
5. Câu hỏi người dùng **không được gửi ra dịch vụ bên ngoài** ở runtime (toàn bộ model self-host).

---

## 2. Kiến trúc

### 2.1 Chạy LLM: Mac (dev) vs GPU server (prod)

Nguyên tắc: **một LLM client, đổi môi trường chỉ bằng biến `.env`** (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_STYLE`). Prod gọi vLLM qua API OpenAI-compatible (`LLM_API_STYLE=openai`, tắt thinking bằng `chat_template_kwargs.enable_thinking=false`); dev gọi API gốc `/api/chat` của Ollama (`LLM_API_STYLE=ollama`, `think=false`) vì endpoint `/v1` của Ollama bỏ qua mọi tham số tắt thinking — Qwen3 vẫn suy nghĩ ngầm, tốn hết token.

| Thành phần | Dev (MacBook M1 16GB) | Prod (server GPU) |
|---|---|---|
| LLM | **Ollama chạy native** (GPU Metal), `qwen3:8b` (Q4_K_M, ~5.5GB) | **vLLM** container (CUDA), `Qwen/Qwen3-8B` hoặc lớn hơn tùy VRAM |
| Embedding + Reranker | `model-server` chạy native, `device=mps` | `model-server` container, `device=cuda` |
| Postgres, Qdrant, Redis | Docker Compose | Docker Compose |
| API, web | Native (`uv run`, `pnpm dev`) — hot reload | Docker Compose |

**Vì sao LLM và model-server chạy native trên Mac:** Docker Desktop trên macOS **không truyền GPU Metal vào container** → model trong Docker chỉ chạy CPU, chậm 5–10 lần.

Ngân sách RAM dev: LLM ~5.5GB + bge-m3 ~1.2GB + reranker ~1.2GB + Docker ~2GB. Fallback: `qwen3:4b-instruct` (không dùng tag `qwen3:4b` — tag này là Qwen3-4B-**Thinking**-2507, luôn suy nghĩ, không tắt được).
Cùng họ model ở dev và prod. Kết quả eval **chính thức** chỉ lấy trên prod (GPU).

### 2.2 Sơ đồ thành phần

```
 Browser ──▶ Caddy (TLS) ──▶ web (Next.js) ──▶ api (FastAPI) ──▶ LLM (Ollama/vLLM)
                                                   │
                         ┌──────────────┬──────────┴───┬──────────────┐
                         ▼              ▼              ▼              ▼
                    Postgres         Qdrant      model-server       Redis
                 (nguồn sự thật:   (index)     (embed + rerank)  (rate limit,
                  văn bản, điều                                   cache, hàng
                  khoản, chunks,                                  đợi sinh)
                  log)

 CLI `lawqa ingest` (người vận hành) ──▶ Postgres + model-server + Qdrant
```

### 2.3 Module map (một codebase, build theo thứ tự)

| Module id | Trách nhiệm | Phụ thuộc |
|---|---|---|
| `platform` | Config, logging, DB, migrations, rate limit, cache, docker/compose | — |
| `model-server` | Embedding (dense) & rerank qua HTTP | — |
| `ingestion` | DOCX → chuẩn hóa → parse cấu trúc & metadata → chunk → index; CLI | platform, model-server |
| `query-understanding` | Phân loại ý định, chuyển ngôn ngữ đời thường → thuật ngữ luật, trích Điều/Khoản | platform |
| `retrieval` | Hybrid search (dense + BM25, đa truy vấn) + RRF + rerank + tra thẳng Điều | platform, model-server |
| `generation` | Prompt theo ý định, gọi LLM, streaming, kiểm tra trích dẫn | platform |
| `pipeline` | Interface `RAGPipeline` + `HybridRAGPipeline` | query-understanding, retrieval, generation |
| `api` | `/ask` SSE, feedback, nguyên văn, danh sách văn bản, giới hạn đồng thời | pipeline |
| `web` | Trang hỏi đáp, panel trích dẫn, lịch sử local | api |
| `eval` | Golden set, metric, báo cáo so sánh | pipeline |

Build order: `platform`, `model-server` → `ingestion` → `query-understanding`, `retrieval` → `generation` → `pipeline` → `api`, `eval` → `web`

### 2.4 Hợp đồng then chốt cho việc so sánh 3 branch

```python
class RAGPipeline(Protocol):
    name: str  # "hybrid" | "hybrid_graph" | "agentic"

    async def retrieve(self, query: Query) -> list[RetrievedChunk]: ...
    def answer(self, query: Query) -> AsyncIterator[PipelineEvent]: ...
```

- `ingestion`, API, web, eval **dùng chung** cho cả 3 branch.
- Branch sau **thêm** pipeline mới bên cạnh (không xóa), chọn bằng `RAG_PIPELINE=hybrid|hybrid_graph|agentic` → ở branch 3 chạy được cả 3 trên cùng build, cùng index.

---

## 3. Thiết kế chi tiết

### 3.1 Dữ liệu (Postgres là nguồn sự thật)

| Bảng | Nội dung |
|---|---|
| `documents` | `so_hieu` (unique, `45/2013/QH13`), tên, loại VB, cơ quan, ngày thông qua, `effective_date`, `expiry_date` (null), file nguồn, `sha256`, `aliases` (vd "Luật Đất đai", "Luật Đất đai 2013") |
| `provisions` | Một Điều/Khoản/Điểm: `document_id`, `path` (`dieu-100/khoan-1/diem-a` — số Điều là duy nhất trong văn bản; Chương/Mục lưu thành thuộc tính), cấp, số, tiêu đề (với Điều), `text` nguyên văn, `valid_from`, `valid_to` (null) |
| `chunks` | Đơn vị index: id, `document_id`, danh sách provision, `text` hiển thị, `context_text` (cho embedding/BM25), số token, `valid_from`, `valid_to` |
| `queries` | Log truy vấn (mục 3.6) |
| `feedback` | 👍/👎 + ghi chú theo `query_id` |

- Qdrant rebuild được hoàn toàn từ Postgres bằng `lawqa reindex`.
- **Chừa chỗ cho giai đoạn sau:** `valid_from`/`valid_to` đã có trên provision, chunk và payload Qdrant, và retrieval đã lọc theo hiệu lực tại ngày hôm nay. Với một văn bản thì lọc này luôn đúng; khi thêm cơ chế cập nhật văn bản (mục 13) chỉ cần thêm bảng quan hệ và logic tính hiệu lực, không phải đổi retrieval hay index.

### 3.2 Ingestion (CLI)

```bash
lawqa ingest raw_data/Luật-45-2013-QH13.docx --dry-run   # xem trước: metadata, số Chương/Điều/Khoản/Điểm, số chunk, cảnh báo parse
lawqa ingest raw_data/Luật-45-2013-QH13.docx             # nạp thật
```

1. **Đọc DOCX** (python-docx): đoạn văn + bảng theo đúng thứ tự (`.doc` → chuyển sang `.docx` bằng LibreOffice headless nếu gặp).
2. **Chuẩn hóa:** Unicode **NFC**, gộp khoảng trắng, bỏ phần quốc hiệu/tiêu ngữ, phần chữ ký cuối văn bản.
3. **Metadata:** số hiệu (`Luật số: 45/2013/QH13`), loại, tên, ngày thông qua (cuối văn bản), ngày hiệu lực (điều "Hiệu lực thi hành").
4. **Parse cấu trúc** bằng state machine **dựa trên text, không dựa vào style Word**: `Chương` đánh số Ả Rập hoặc La Mã (`Chương 1.` / `Chương I`) + dòng tên chương; `Mục`; `Điều N. {tiêu đề}`; khoản `1.`; điểm theo bảng chữ cái tiếng Việt (`a) b) c) d) đ) e) g) h) i) k) l) m) n) o) p) q) r) s) t) u) v) x) y)`); đoạn không đánh số trong khoản/Điều được giữ với đơn vị cha.
5. **Kiểm tra tính toàn vẹn:** số Điều liên tục 1..N, không trùng, không mất đoạn (tổng ký tự sau parse ≈ trước parse); vi phạm → dừng, in vị trí lỗi.
6. **Chunking theo cấu trúc:** đơn vị = **1 Điều**; Điều > `CHUNK_MAX_TOKENS` (512) → tách theo Khoản (gộp các Khoản ngắn liền nhau); Khoản vẫn quá dài → tách theo Điểm. Mỗi chunk prepend ngữ cảnh `"Luật Đất đai (45/2013/QH13) > Chương 7. … > Điều 100. {tiêu đề}"` vào `context_text`; `text` hiển thị giữ nguyên văn.
7. **Index:** point id = `uuid5(document_id, chunk_path)`; 2 named vectors `dense` + `bm25`; payload `so_hieu`, `dieu`, `khoan`, `chuong`, `valid_from`, `valid_to`.
8. **Idempotent:** cùng `sha256` → bỏ qua; cùng `so_hieu` nhưng file khác → yêu cầu `--replace` (xóa dữ liệu cũ của văn bản đó rồi nạp lại trong một transaction).
9. Báo cáo cuối: số Chương/Điều/Khoản/Điểm/chunk, phân bố độ dài chunk, thời gian.

Lệnh khác: `lawqa documents list|show|remove <so_hieu>`, `lawqa reindex`.

### 3.3 Query understanding (1 lần gọi LLM, output JSON có schema)

Kết quả: `intent` ∈ {`situation`, `lookup`, `topic_search`, `procedure`, `out_of_scope`}; `legal_query` (câu hỏi viết lại bằng thuật ngữ pháp lý); `citations` (Điều/Khoản/Điểm được nêu); `missing_facts` (với `situation`).

- **Từ điển đồng nghĩa đất đai** (`resources/dat_dai_synonyms.yaml`, có review): sổ đỏ/sổ hồng → giấy chứng nhận quyền sử dụng đất; đất thổ cư → đất ở; đất ruộng → đất trồng lúa; xây nhà trên đất nông nghiệp → sử dụng đất không đúng mục đích… Áp dụng bằng luật để mở rộng truy vấn BM25.
- Trích Điều/Khoản/Điểm **chỉ bằng regex** ("Điều 100", "khoản 2 Điều 5", "điểm a khoản 1 Điều 100"). `lookup` do regex quyết định: có nêu Điều → `lookup`, không nêu → không phải `lookup`. Câu hỏi ngôi thứ nhất ("tôi", "nhà mình"…) bị gán `topic_search` → chuyển thành `situation`.
- JSON lỗi / timeout → fallback: có nêu Điều → `lookup`, không → `topic_search`; `legal_query` = câu gốc (không chặn luồng trả lời).
- `out_of_scope` **vẫn chạy retrieval để kiểm chứng**: nếu nguồn tốt nhất (rerank/lookup) có điểm ≥ `OUT_OF_SCOPE_OVERRIDE_SCORE` (0.5) thì bỏ nhãn, xử lý như `topic_search`; ngược lại → câu từ chối cố định, không gọi LLM sinh.
- `legal_query` **không dùng để tìm kiếm theo mặc định** (`SEARCH_WITH_LEGAL_QUERY=false`): trên seed set, thêm nó làm Recall@10 nhóm `layperson` giảm (.889 → .833 với `hybrid+rerank`). Vẫn sinh ra để ghi log và làm ablation.
- Tắt được bằng config để làm ablation.

### 3.4 Retrieval

```
câu gốc ───────────────┐
legal_query (tuỳ chọn)─┼─▶ mỗi câu: dense (top 50) + BM25 (top 50) ─▶ RRF gộp (top 40)
mở rộng đồng nghĩa ────┘                                 (lọc hiệu lực tại hôm nay)
citations ─▶ tra thẳng chunk theo Điều/Khoản ─▶ chèn đầu danh sách
                                    ▼
             rerank bge-reranker-v2-m3 (điểm cao nhất trên các câu truy vấn) → top 8
                                    ▼
             điểm cao nhất < RERANK_MIN_SCORE → "không đủ căn cứ"
                                    ▼
             context packing: gom theo Điều, sắp theo thứ tự Điều, ≤ CONTEXT_MAX_TOKENS (6000)
```

- **Dense:** BGE-M3, 1024 chiều, cosine.
- **BM25:** sparse vector Qdrant `modifier: idf` (Qdrant tính IDF); ta tính phần TF theo BM25 (`k1=1.2, b=0.75`). Tokenizer: lowercase + NFC, **unigram + bigram âm tiết**, giữ nguyên định danh pháp lý (`45/2013/qh13`, `điều 100`) thành một token; hash `mmh3` 32-bit. Cùng tokenizer khi index và query.
- Mọi tham số trong config, được log theo từng truy vấn.
- **Ablation bắt buộc:** `dense-only`, `bm25-only`, `hybrid`, `hybrid+rerank`, `hybrid+rerank+query-understanding`.

### 3.5 Generation

- Prompt tiếng Việt, **template theo intent** (`generation/prompts/*.jinja`):
  - `situation`: **Kết luận ngắn** (Có / Không / Tùy trường hợp) → giải thích dễ hiểu theo từng điều kiện → hậu quả pháp lý nếu nguồn có (mức phạt cụ thể không có trong dữ liệu → nói rõ) → thông tin nên bổ sung → căn cứ pháp lý.
  - `lookup`: nguyên văn Điều/Khoản + tóm tắt ngắn.
  - `topic_search`: liệt kê quy định liên quan, mỗi ý một trích dẫn.
  - `procedure`: các bước, hồ sơ, cơ quan, thời hạn — có trích dẫn.
  - `out_of_scope`: câu từ chối cố định, không gọi LLM sinh dài.
- Luật chung: **chỉ** dựa trên nguồn được cung cấp, không dùng kiến thức bên ngoài về luật khác/luật mới hơn; mỗi nhận định gắn `[n]`; giải thích thuật ngữ khi trả lời câu đời thường; luôn kèm miễn trừ "thông tin tham khảo, không thay thế tư vấn pháp lý".
- `temperature=0.1`, tắt thinking mode của Qwen3.
- **Kiểm tra trích dẫn sau sinh:** `[n]` phải trỏ tới nguồn đã cung cấp; không hợp lệ → loại và ghi metric.
- Timeout + retry có backoff; lỗi trả SSE `error`, không treo kết nối.

### 3.6 API (FastAPI, prefix `/api/v1`, không xác thực)

| Method | Path | Mô tả |
|---|---|---|
| POST | `/ask` | `{question}` → **SSE stream** |
| POST | `/queries/{id}/feedback` | 👍/👎 + ghi chú (id là UUID khó đoán) |
| GET | `/chunks/{id}` | Nguyên văn + vị trí (Chương/Điều/Khoản) |
| GET | `/documents` | Văn bản trong corpus + ngày hiệu lực |
| GET | `/healthz`, `/readyz` | Liveness / readiness (DB, Qdrant, Redis, LLM, model-server) |
| GET | `/metrics` | Prometheus — **chỉ mạng nội bộ** |

SSE contract cho `/ask`:
```
event: meta     data: {"query_id":"…","pipeline":"hybrid","intent":"situation"}
event: sources  data: [{"n":1,"chunk_id":"…","so_hieu":"45/2013/QH13","dieu":"100","khoan":"1","title":"…","snippet":"…","score":0.91}]
event: token    data: {"delta":"…"}
event: done     data: {"citations":[1,3],"missing_facts":["…"],"usage":{…},"latency_ms":{…},"cached":false}
event: error    data: {"code":"BUSY","message":"Hệ thống đang bận, vui lòng thử lại sau ít phút."}
```

**Bảo vệ hệ thống public:** rate limit theo IP (Redis) 10 câu/phút, 100 câu/ngày; câu hỏi ≤ 1.000 ký tự; `MAX_CONCURRENT_GENERATIONS` = 16, chờ tối đa 30s rồi trả `BUSY`; **cache** câu trả lời (Redis, TTL 24h, khóa = hash(câu hỏi chuẩn hóa + pipeline + config hash + `corpus_version`)) — `corpus_version` tăng mỗi lần ingest/remove nên cache tự vô hiệu; CORS chỉ cho domain web.

**Log & quyền riêng tư:** bảng `queries` lưu câu hỏi, intent, legal_query, pipeline, config hash, `corpus_version`, chunk ids + điểm từng giai đoạn, câu trả lời, trích dẫn, latency, token, model, git SHA, cache hit, `ip_hash` (HMAC có salt, **không lưu IP thô**). Giữ 90 ngày, job dọn hằng ngày. Giao diện có thông báo: câu hỏi được lưu ẩn danh, không nên nhập thông tin cá nhân.

### 3.7 Web (Next.js)

- `/` = trang hỏi đáp: ô nhập, câu hỏi gợi ý cho cả hai kiểu người dùng, câu trả lời streaming, trích dẫn `[n]` mở panel nguyên văn.
- Câu trả lời `situation` có khối "Kết luận" nổi bật và khối "Thông tin nên bổ sung".
- Lịch sử: sidebar lưu `localStorage`, xóa được.
- Footer: văn bản đang áp dụng (Luật Đất đai 45/2013/QH13), miễn trừ trách nhiệm, thông báo quyền riêng tư.
- Responsive (ưu tiên mobile), tiếng Việt, WCAG AA cơ bản (keyboard, contrast, `aria-live` cho vùng streaming).

### 3.8 Eval

- Golden set có sẵn → `eval/datasets/golden.jsonl`:
  `{"id","question","reference_answer","reference_citations":[{"dieu","khoan"?,"diem"?}],"intent","persona":"layperson|professional","tags":[…]}`
- Metric:
  - Retrieval: Recall@5/10, MRR@10, nDCG@10.
  - Generation (LLM-as-judge, judge **cố định cho cả 3 branch**): faithfulness, answer correctness, citation precision/recall, refusal đúng/sai, độ dễ hiểu (với `layperson`).
  - Vận hành: latency p50/p95 (understanding, retrieve, rerank, TTFT, total), tokens/câu.
- Mọi metric chia theo `persona` và `intent`.
- Output: `eval/results/{pipeline}-{git_sha}-{timestamp}.json` + `report.md`; `make eval-compare` gộp bảng so sánh.

### 3.9 Vận hành production

- `compose.prod.yml`: caddy (TLS), web, api, model-server (CUDA), vLLM, postgres, qdrant, redis — healthcheck, restart policy, giới hạn tài nguyên, volume bền vững.
- Service `ops` (profile `tools`): cùng image api, mount `raw_data/` → chạy `lawqa` trên prod.
- Migration Alembic chạy one-shot trước khi api khởi động.
- Backup: `pg_dump` hằng ngày (Qdrant rebuild được bằng `lawqa reindex`).
- Log JSON có `request_id`/`query_id`; Prometheus metrics (latency từng stage, lỗi LLM, hàng đợi, rate-limit hits, cache hit rate).

---

## 4. Tech Stack

| Lớp | Lựa chọn |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + asyncpg, Alembic, httpx, structlog, typer (CLI), python-docx, mmh3, redis-py |
| Model server | FastAPI + FlagEmbedding (`BAAI/bge-m3`, `BAAI/bge-reranker-v2-m3`), PyTorch (mps/cuda/cpu) |
| LLM | Ollama (dev) / vLLM (prod); client tự viết bằng httpx (`generation/llm_client.py`) — SDK `openai` 3.x dùng httpx2 và không có các tham số tắt thinking riêng của Ollama/vLLM |
| Data | PostgreSQL 16, Qdrant (≥ 1.12: Query API, sparse IDF), Redis 7 |
| Frontend | Next.js (App Router, bản stable mới nhất lúc scaffold), TypeScript strict, Tailwind CSS, shadcn/ui, pnpm |
| Tooling | uv, ruff, mypy (strict cho `src/`), pytest, testcontainers, Vitest, Playwright, pre-commit |
| Deploy | Docker Compose, Caddy, NVIDIA Container Toolkit |

Phiên bản cụ thể được pin trong `uv.lock` / `pnpm-lock.yaml` khi scaffold.

---

## 5. Commands

```bash
# Một lần
make setup                     # uv sync (backend, model-server), pnpm install (web), pre-commit install
brew install ollama && ollama pull qwen3:8b
make models                    # tải bge-m3 + bge-reranker-v2-m3

# Dev hằng ngày (Mac)
make infra-up                  # docker compose -f compose.dev.yml up -d   (postgres, qdrant, redis)
make migrate                   # cd backend && uv run alembic upgrade head
make dev-models                # cd model-server && uv run uvicorn model_server.main:app --port 8001   (MPS)
make dev-api                   # cd backend && uv run uvicorn lawqa.main:app --reload --port 8000
make dev-web                   # cd web && pnpm dev   (port 3000)

# Nạp dữ liệu (sau khi hệ thống đã chạy)
make ingest FILE=raw_data/Luật-45-2013-QH13.docx ARGS=--dry-run
make ingest FILE=raw_data/Luật-45-2013-QH13.docx
make reindex                   # rebuild Qdrant từ Postgres

# Chất lượng
make lint                      # ruff check . && ruff format --check . && pnpm -C web lint
make typecheck                 # mypy backend/src model-server/src && pnpm -C web typecheck
make test                      # pytest -q && pnpm -C web test
make test-e2e                  # pnpm -C web exec playwright test
make eval SET=eval/datasets/golden.jsonl PIPELINE=hybrid
make eval-compare

# Production (máy GPU)
make prod-up                   # docker compose -f compose.prod.yml --env-file .env.prod up -d
make prod-ingest FILE=…        # docker compose -f compose.prod.yml --profile tools run --rm ops lawqa ingest …
make prod-logs
make backup
```

---

## 6. Project Structure

```
chatbot-law/
├── SPEC.md
├── Makefile
├── compose.dev.yml             # postgres, qdrant, redis
├── compose.prod.yml            # toàn bộ stack + vLLM + caddy + ops (profile tools)
├── .env.example
├── raw_data/                   # văn bản gốc (giai đoạn này chỉ nạp 45/2013)
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── src/lawqa/
│   │   ├── main.py             # FastAPI app factory
│   │   ├── cli.py              # typer: ingest, documents, reindex, eval
│   │   ├── core/               # config, logging, errors, rate_limit, cache
│   │   ├── db/                 # models, session, repositories
│   │   ├── ingestion/          # docx_reader.py, normalize.py, legal_parser.py, metadata.py,
│   │   │                       # integrity.py, chunker.py, indexer.py
│   │   ├── understanding/      # classifier.py, synonyms.py, citation_regex.py
│   │   ├── retrieval/          # bm25_tokenizer.py, hybrid.py, rerank.py, filters.py,
│   │   │                       # citation_lookup.py, context_packer.py
│   │   ├── generation/         # llm_client.py, prompts/, citations.py
│   │   ├── pipelines/          # base.py (RAGPipeline), hybrid.py   ← branch sau thêm graph.py, agentic.py
│   │   ├── api/                # routers/, schemas/, sse.py, concurrency.py
│   │   └── eval/               # runner.py, metrics/, judge.py, report.py
│   ├── resources/              # dat_dai_synonyms.yaml
│   └── tests/
│       ├── unit/
│       ├── integration/        # Postgres/Qdrant/Redis thật qua testcontainers
│       ├── acceptance/         # chạy trên raw_data/Luật-45-2013-QH13.docx
│       └── fixtures/           # trích đoạn từ luật 2013
├── model-server/
│   └── src/model_server/       # /embed, /rerank, /healthz
├── web/
│   ├── src/app/                # / (hỏi đáp)
│   ├── src/components/
│   ├── src/lib/                # api client, SSE parser, local history
│   └── tests/
├── eval/
│   ├── datasets/               # golden.jsonl
│   └── results/
├── deploy/                     # Caddyfile, vllm args, backup scripts
└── docs/adr/
```

---

## 7. Code Style

Python: async xuyên suốt I/O, type đầy đủ, Pydantic cho dữ liệu qua ranh giới, dependency injection qua constructor (dễ thay fake khi test), không hardcode model/URL/ngưỡng.

```python
class HybridRetriever:
    def __init__(self, qdrant: AsyncQdrantClient, encoder: EncoderClient, settings: RetrievalSettings) -> None:
        self._qdrant = qdrant
        self._encoder = encoder
        self._settings = settings

    async def search(self, texts: list[str], reference_date: date) -> list[RetrievedChunk]:
        s = self._settings
        dense_vectors = await self._encoder.embed_dense(texts)
        prefetch = [
            p
            for text, dense in zip(texts, dense_vectors, strict=True)
            for p in (
                models.Prefetch(query=dense, using="dense", limit=s.dense_top_k),
                models.Prefetch(query=bm25_encode(text), using="bm25", limit=s.sparse_top_k),
            )
        ]
        result = await self._qdrant.query_points(
            collection_name=s.collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=valid_at(reference_date),
            limit=s.fused_top_k,
            with_payload=True,
        )
        return [RetrievedChunk.from_point(p, stage="fused") for p in result.points]
```

Quy ước:
- Python: `snake_case` hàm/biến, `PascalCase` class, module nhỏ theo trách nhiệm; ruff format (line 100); exception nghiệp vụ trong `core/errors.py`, map sang HTTP ở một chỗ.
- Identifier tiếng Anh; prompt và thông báo cho người dùng tiếng Việt. Trường metadata pháp lý giữ tên Việt không dấu (`so_hieu`, `dieu`, `khoan`, `diem`).
- Chỉ comment chỗ logic phức tạp (regex parse cấu trúc luật, công thức BM25).
- TypeScript: strict, server components mặc định; gọi API qua một client duy nhất trong `src/lib`.

---

## 8. Testing Strategy

| Mức | Công cụ | Nội dung |
|---|---|---|
| Unit | pytest | NFC; parser Chương (Ả Rập & La Mã)/Điều/Khoản/Điểm (gồm `đ)`), đoạn không đánh số; metadata; kiểm tra toàn vẹn; chunker (Điều ngắn, Điều rất dài); tokenizer BM25; đồng nghĩa; regex trích dẫn; prompt builder; kiểm tra trích dẫn |
| Integration | pytest + testcontainers | Ingest → index → hybrid search; ingest lại cùng file không trùng; `--replace`; API `/ask` SSE; rate limit; giới hạn đồng thời; cache vô hiệu khi `corpus_version` đổi. LLM & model-server dùng **fake** cho kết quả xác định |
| Acceptance | pytest (marker `corpus`) | Nạp `raw_data/Luật-45-2013-QH13.docx` thật: đúng 14 Chương, 212 Điều liên tục; mọi chunk ≤ `CHUNK_MAX_TOKENS`; nguyên văn ghép lại từ provision khớp văn bản gốc; tra "Điều 100" trả đúng Điều 100 |
| Retrieval regression | pytest | ~30 câu hỏi có đáp án Điều trên luật 2013; assert Recall@10 ≥ ngưỡng |
| Frontend | Vitest + Testing Library | SSE parser, trích dẫn, lịch sử localStorage |
| E2E | Playwright | Hỏi → stream + trích dẫn → mở nguyên văn; câu ngoài phạm vi bị từ chối; mobile |
| Eval | `make eval` | Golden set; chạy thủ công/định kỳ (tốn GPU) |

- Coverage ≥ 80% cho `ingestion/`, `understanding/`, `retrieval/`, `generation/`, `pipelines/`; ≥ 70% toàn backend.
- Test không phụ thuộc Ollama/GPU (CI chạy trên máy không GPU).
- Bug fix luôn kèm test tái hiện.

---

## 9. Boundaries

**Always**
- Chạy `make lint typecheck test` trước mỗi commit.
- Chuẩn hóa NFC mọi text trước khi index và trước khi query.
- Mọi câu trả lời có trích dẫn hợp lệ hoặc nói rõ "không đủ căn cứ"; luôn có miễn trừ trách nhiệm.
- Trả lời chỉ từ corpus, không từ kiến thức sẵn có của LLM.
- Cấu hình qua env (`pydantic-settings`), cập nhật `.env.example` khi thêm biến.
- Ghi git SHA + config hash vào mọi kết quả eval.
- Dùng cùng golden set, cùng judge, cùng phần cứng khi so sánh các branch.

**Ask first**
- Thêm dependency hoặc service mới ngoài spec (vd CAPTCHA).
- Đổi embedding model, chiến lược chunking, tokenizer BM25 (bắt buộc reindex, mất tính so sánh).
- Đổi interface `RAGPipeline` hoặc SSE contract.
- Thay đổi schema DB sau khi migration đầu tiên đã merge.
- Thay đổi chính sách lưu log / thời hạn giữ dữ liệu.
- Nạp thêm văn bản ngoài Luật 45/2013 ở giai đoạn này.
- Tạo/push branch lên remote, sửa CI.

**Never**
- Commit secrets, file `.env*` thật, golden set nếu là dữ liệu nội bộ.
- Gửi câu hỏi người dùng tới dịch vụ bên ngoài ở runtime; lưu IP thô.
- Trình bày câu trả lời như tư vấn pháp lý chính thức.
- Sửa golden set hoặc metric để "đẹp số"; xóa / skip test đang fail mà không được duyệt.
- Hardcode tên model, URL, ngưỡng trong code.

---

## 10. Success Criteria (giai đoạn này hoàn thành khi)

1. **Dev trên Mac:** từ máy sạch, làm theo README trong ≤ 30 phút là hỏi được câu đầu tiên; LLM chạy qua Ollama Metal.
2. **Ingestion Luật 45/2013:** đúng 14 Chương, 212 Điều; nguyên văn ghép lại khớp văn bản gốc (sau chuẩn hóa); số hiệu, ngày hiệu lực 01/07/2014 đúng; nạp lại cùng file không tạo bản trùng.
3. **Retrieval:** trên golden set, `hybrid+rerank` có Recall@10 và nDCG@10 cao hơn cả `dense-only` và `bm25-only`; query understanding cải thiện Recall@10 trên nhóm `layperson`. Ngưỡng tuyệt đối đề xuất Recall@10 ≥ 0.85 — chốt sau lần chạy baseline. Tra cứu đích danh "Điều N" đúng 100%.
4. **Generation:** `invalid_citation_rate` = 0; faithfulness ≥ 0.9; câu ngoài phạm vi bị từ chối đúng ≥ 95%; câu `situation` luôn có Kết luận + căn cứ.
5. **Hiệu năng prod (GPU):** retrieval + rerank p95 ≤ 500ms; TTFT p95 ≤ 3s; 20 người dùng đồng thời không lỗi; quá tải trả `BUSY` thay vì treo.
6. **Production:** `make prod-up` trên máy GPU sạch đưa stack lên healthy; có TLS, rate limit, backup, metrics nội bộ; restart không mất dữ liệu.
7. **Chất lượng code & eval:** lint, typecheck, test, acceptance, E2E pass; coverage đạt mục 8; `make eval` sinh báo cáo đủ metric mục 3.8 — baseline cho branch 2 và 3.

---

## 11. Git & branch

- `main`: spec + tài liệu chung.
- `approach/hybrid-rag`: toàn bộ branch 1 (checkout từ `main`).
- `approach/hybrid-graph-rag`: checkout từ `approach/hybrid-rag` khi branch 1 đạt Success Criteria.
- `approach/agentic-rag`: checkout từ `approach/hybrid-graph-rag`.
- Commit nhỏ, Conventional Commits (`feat(ingestion): ...`).

---

## 12. Open Questions

1. **Golden set:** định dạng hiện tại, số câu, có viết cho Luật 2013 không, có ghi Điều/Khoản tham chiếu và phân biệt người dân/chuyên môn không?
2. **GPU production:** loại GPU / VRAM? → quyết định model prod.
3. **Judge cho eval:** chạy model lớn local trên máy GPU, hay được gửi golden set (không phải dữ liệu người dùng) tới API bên ngoài?
4. **Log câu hỏi:** đồng ý lưu ẩn danh 90 ngày?
5. **Commit `raw_data/` vào git:** văn bản quy phạm pháp luật không thuộc đối tượng bảo hộ quyền tác giả → đề xuất commit để acceptance test chạy ở mọi nơi.
6. **Chống bot:** rate limit theo IP là đủ, hay cần thêm CAPTCHA?
7. Domain/hostname production?

---

## 13. Giai đoạn sau: cập nhật văn bản (đã phân tích, chưa làm)

Ghi lại để không mất kết quả phân tích 3 file còn lại trong `raw_data/`; sẽ viết spec chi tiết khi bắt đầu.

| Văn bản | Loại | Việc hệ thống cần làm |
|---|---|---|
| Luật 31/2024/QH15 | Thay thế toàn bộ Luật 45/2013 | Quan hệ cấp văn bản + ngày hiệu lực (tự động); ánh xạ Điều cũ ↔ Điều mới (tự đề xuất bằng so khớp ngữ nghĩa + LLM, người duyệt mục độ tin cậy thấp); hiệu lực riêng theo Điều (Điều 190, 248) và theo điều kiện (khoản 9 Điều 60) |
| Luật 43/2024/QH15 | Sửa đổi Luật 31/2024 | Parse 4 chỉ thị ("sửa đổi, bổ sung khoản/khổ đầu khoản … như sau") → bản hợp nhất; sửa khoản 1 Điều 252 nên **ngày hiệu lực Luật 31/2024 đổi 01/01/2025 → 01/08/2024** → tính lại dây chuyền hiệu lực; 3 chỉ thị sửa luật ngoài corpus → bỏ qua có báo cáo |
| NQ 254/2025/QH15 | Cơ chế đặc thù, ưu tiên áp dụng | Không sửa chữ của luật; quan hệ `overrides` từ 01/01/2026; liên kết tới ~30 Điều/Khoản được trích tường minh; đề xuất liên kết cho phần điều chỉnh không trích dẫn |

Các thành phần dự kiến: bảng `document_relations`, `provision_versions`, `provision_links`, `effective_rules`, `changesets` (nháp → duyệt → phát hành → hoàn tác); CLI `lawqa changeset …`; cảnh báo văn bản sửa đổi chưa có trong corpus. Giai đoạn này đã chừa sẵn `valid_from`/`valid_to` và lọc theo hiệu lực trong retrieval nên không phải làm lại phần tìm kiếm.
