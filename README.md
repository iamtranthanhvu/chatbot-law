# Hỏi đáp Luật Đất đai

Hệ thống hỏi đáp pháp luật đất đai tiếng Việt: người dùng đặt câu hỏi, hệ thống tìm Điều/Khoản liên quan
và trả lời có trích dẫn. Hiện chỉ nạp **Luật Đất đai 2013 (45/2013/QH13)**. Nhánh này dùng Hybrid RAG
(BM25 + vector + rerank). Thiết kế chi tiết: [`SPEC.md`](SPEC.md); tiến độ: [`tasks/todo.md`](tasks/todo.md).

```
web (Next.js, :3000) ──/api──▶ backend (FastAPI, :8000) ──▶ Postgres (:5432) · Qdrant (:6333) · Redis (:6379)
                                       │
                                       ├──▶ model-server (BGE-M3 + reranker, :8001)
                                       └──▶ Ollama (LLM, :11434)
```

Hướng dẫn dưới đây dành cho máy dev **macOS Apple Silicon** (đã chạy thử trên M1 16 GB). Linux/Windows
chưa được thử; không có GPU thì model-server chạy CPU, chậm hơn nhiều.

## 1. Cài công cụ (một lần trên máy)

| Công cụ | Dùng cho | Cài |
|---|---|---|
| Docker Desktop | Postgres, Qdrant, Redis và test integration | https://www.docker.com/products/docker-desktop |
| uv | Python 3.12 + thư viện backend, model-server (uv tự tải Python) | `brew install uv` |
| nvm | Node 24 cho web (bản cố định trong `.nvmrc`) | `brew install nvm` rồi làm theo hướng dẫn brew in ra |
| Ollama | Chạy LLM trên máy | `brew install ollama` |

pnpm không cần cài: Makefile gọi qua `corepack` đi kèm Node.

Cần khoảng **15 GB** đĩa trống và mạng ổn định — lần đầu tải khoảng 10 GB (model ~8,5 GB, thư viện,
Docker image).

## 2. Setup (một lần sau khi clone)

Mở Docker Desktop và Ollama trước (`brew services start ollama`, hoặc mở app Ollama), rồi chạy ở thư mục gốc repo:

```bash
nvm install && nvm use          # Node 24 theo .nvmrc
make setup                      # tạo .env từ .env.example, cài thư viện Python + web (~5–10 phút)
```

**Sửa `.env`** (file này không được commit):

```bash
LLM_MODEL=qwen3:4b-instruct     # .env.example ghi qwen3:8b — quá nặng cho máy 16 GB
IP_HASH_SECRET=<chuỗi ngẫu nhiên>   # tạo bằng: openssl rand -hex 32
```

> Dùng đúng tag `qwen3:4b-instruct`. Tag `qwen3:4b` là bản "thinking", trả lời chậm hơn nhiều.

Tải model và dựng dữ liệu:

```bash
ollama pull qwen3:4b-instruct   # LLM, 2,5 GB
make models                     # BGE-M3 + bge-reranker-v2-m3 từ Hugging Face, ~6 GB (~10–15 phút)
make infra-up                   # chạy Postgres, Qdrant, Redis bằng Docker
make migrate                    # tạo bảng trong Postgres
```

Nạp Luật 2013 — bước này cần model-server đang chạy để tạo embedding, nên mở **terminal riêng**:

```bash
make dev-models                 # terminal 1, để chạy luôn
```

```bash
make ingest FILE=raw_data/Luật-45-2013-QH13.docx    # terminal 2, ~1 phút
make docs                       # kiểm tra: phải thấy 45/2013/QH13
```

Kết quả đúng: 212 Điều, 279 chunk. Nạp lại cùng file không tạo bản trùng.

## 3. Chạy hằng ngày

Docker Desktop và Ollama đang mở, rồi mỗi lệnh một terminal (terminal nào chạy web phải `nvm use` trước):

```bash
make infra-up                   # nếu container chưa chạy
make dev-models                 # terminal 1 — model-server :8001 (chờ nạp xong model mới hỏi được)
make dev-api                    # terminal 2 — API :8000
nvm use && make dev-web         # terminal 3 — web :3000
```

Mở http://127.0.0.1:3000.

Kiểm tra nhanh mọi thành phần đã sẵn sàng:

```bash
curl -s http://127.0.0.1:8000/api/v1/readyz
```

Trên M1, một câu trả lời mất khoảng 30–90 giây (LLM chạy trên máy); hỏi lại đúng câu cũ được trả từ cache ngay.

Hỏi thử không cần web:

```bash
cd backend
uv run lawqa search "điều kiện chuyển nhượng quyền sử dụng đất"   # chỉ tìm kiếm, không gọi LLM
uv run lawqa ask "Đất chưa có sổ đỏ có bán được không?"           # trả lời đầy đủ
```

Tắt: `Ctrl+C` ở từng terminal, rồi `make infra-down` (dữ liệu vẫn giữ trong Docker volume).
Xóa sạch dữ liệu để nạp lại từ đầu: `docker compose -f compose.dev.yml down -v`.

## 4. Test và kiểm tra code

```bash
make lint typecheck             # ruff, mypy, eslint, tsc
make test                       # unit + integration (cần Docker đang chạy) + Vitest
```

Test E2E của web (Playwright, chạy với API giả, không cần backend) cần tải Chromium một lần:

```bash
cd web && PLAYWRIGHT_BROWSERS_PATH=0 corepack pnpm exec playwright install chromium && cd ..
make test-e2e
```

Test với model và LLM thật (chậm, cần model-server/Ollama): `make test-models`,
`cd backend && uv run pytest -m llm`.

Đánh giá chất lượng (eval): `make eval MODE=retrieval`, kết quả ghi vào `eval/results/`.

## 5. Cấu trúc thư mục

```
backend/        FastAPI + CLI `lawqa` (nạp văn bản, tìm kiếm, pipeline RAG, eval) — Python 3.12, uv
model-server/   Dịch vụ embedding + rerank (BGE-M3, bge-reranker-v2-m3)
web/            Giao diện Next.js
raw_data/       Văn bản luật gốc (.docx)
eval/           Bộ câu hỏi đánh giá và kết quả
tasks/          Kế hoạch và danh sách việc
compose.dev.yml Postgres, Qdrant, Redis cho dev
```

## 6. Lỗi thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| `make infra-up` báo cổng 5432/6379 đã dùng | Postgres/Redis cài sẵn trên máy đang chạy — tắt chúng (`brew services stop postgresql`) |
| `make dev-web` hoặc `make test` lỗi ở phần web | Node sai bản — chạy `nvm use` trong terminal đó |
| Hỏi bị lỗi, log API báo không tìm thấy model | Chưa `ollama pull` đúng model ghi trong `LLM_MODEL` của `.env`, hoặc Ollama chưa chạy |
| `make ingest` báo không kết nối được model-server | Chưa chạy `make dev-models` |
| Mọi câu đều nhận "Không tìm thấy căn cứ trong dữ liệu hiện có…" | Chưa nạp dữ liệu — xem `make docs` |
| `/readyz` trả 503 | Xem thành phần bị lỗi trong JSON trả về và bật lại nó |

## Lưu ý

- Không commit `.env`.
- Câu trả lời chỉ mang tính tham khảo; hệ thống chưa gồm Luật Đất đai 2024.
