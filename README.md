# Hỏi đáp Luật Đất đai

Hệ thống hỏi đáp pháp luật đất đai tiếng Việt: người dùng đặt câu hỏi, hệ thống tìm Điều/Khoản liên quan
và trả lời có trích dẫn. Corpus mẫu gồm **Luật Đất đai 2024 (31/2024/QH15), Luật 43/2024/QH15,
Nghị quyết 254/2025/QH15** và Luật 45/2013/QH13 để tra cứu lịch sử. Đây chưa phải kho pháp luật đầy đủ:
nghị định, thông tư và văn bản địa phương chưa được nạp. Nhánh này dùng Hybrid RAG
(BM25 + vector + rerank). Thiết kế chi tiết: [`SPEC.md`](SPEC.md); tiến độ: [`tasks/todo.md`](tasks/todo.md).

```
web (Next.js, :3000) ──/api──▶ backend (FastAPI, :8000) ──▶ Postgres (:5432) · Qdrant (:6333) · Redis (:6379)
                                       │
                                       ├──▶ model-server (BGE-M3 + reranker, :8001)
                                       └──▶ Ollama (LLM, :11434)
```

Cả ba môi trường dùng **cùng một bộ lệnh `make`**: macOS (đã chạy thử trên M1 16 GB), Linux, và Windows
qua WSL2 (xem mục 1b). Không có GPU thì model-server chạy CPU, chậm hơn nhiều.

## 1. Cài công cụ (một lần trên máy)

| Công cụ | Dùng cho | macOS | Linux / WSL2 (Ubuntu) |
|---|---|---|---|
| Docker | Postgres, Qdrant, Redis và test integration | Docker Desktop: https://www.docker.com/products/docker-desktop | Docker Engine + plugin compose (WSL2: dùng Docker Desktop, xem 1b) |
| make, curl | Chạy lệnh trong Makefile | có sẵn (Xcode CLT) | `sudo apt install -y make curl build-essential` |
| uv | Python 3.12 + thư viện backend, model-server (uv tự tải Python) | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| nvm | Node 24 cho web (bản cố định trong `.nvmrc`) | `brew install nvm` rồi làm theo hướng dẫn brew in ra | script cài chính thức: https://github.com/nvm-sh/nvm#installing-and-updating |
| Ollama | Chạy LLM trên máy | `brew install ollama` | `curl -fsSL https://ollama.com/install.sh \| sh` |

pnpm không cần cài: Makefile gọi qua `corepack` đi kèm Node.

### 1b. Windows: dùng WSL2

Windows không chạy trực tiếp Makefile bash, nên dùng WSL2 để có môi trường Linux và gõ đúng các lệnh như mac/Linux:

1. PowerShell (quyền admin): `wsl --install -d Ubuntu`, khởi động lại máy, tạo user Ubuntu. Cần bật ảo hóa (virtualization) trong BIOS.
2. Cài Docker Desktop, vào Settings → Resources → WSL integration và bật cho Ubuntu.
3. Mở terminal Ubuntu và cài công cụ theo cột "Linux / WSL2" ở bảng trên.
4. **Clone repo bên trong WSL** (ví dụ `~/chatbot-law`), không để ở `/mnt/c/...` (I/O chậm và dễ lỗi quyền file).
5. Từ đây làm đúng các mục 2–4 trong terminal Ubuntu. Mở web bằng trình duyệt Windows tại http://127.0.0.1:3000 (WSL2 tự chuyển tiếp cổng).
6. Ollama: cài bản Linux trong WSL và chạy `ollama serve` (không có `brew services`). Có thể dùng Ollama bản Windows, vẫn giữ `LLM_BASE_URL` trỏ `127.0.0.1:11434`.
7. GPU NVIDIA (nếu có): cài driver Windows mới nhất, WSL2 sẽ dùng được CUDA và `DEVICE=auto` tự nhận. Không có GPU thì chạy CPU, nên giảm `RERANK_CANDIDATES` khi dev.

Cần khoảng **15 GB** đĩa trống và mạng ổn định — lần đầu tải khoảng 10 GB (model embedding, reranker,
Whisper tiếng Việt, thư viện và Docker image).

## 2. Setup (một lần sau khi clone)

Mở Docker và Ollama trước (macOS: `brew services start ollama` hoặc mở app Ollama; Linux/WSL2: `ollama serve` ở một terminal riêng), rồi chạy ở thư mục gốc repo:

```bash
nvm install && nvm use          # Node 24 theo .nvmrc
make setup                      # tạo .env từ .env.example, cài thư viện Python + web (~5–10 phút)
```

**Sửa `.env`** (file này không được commit). `.env.example` đã đặt sẵn `LLM_MODEL=qwen3:4b-instruct`, chỉ cần điền:

```bash
IP_HASH_SECRET=<chuỗi ngẫu nhiên>   # tạo bằng: openssl rand -hex 32
```

> Dùng đúng tag `qwen3:4b-instruct`. Tag `qwen3:4b` là bản "thinking", trả lời chậm hơn nhiều. Máy có nhiều VRAM/RAM có thể đổi sang `qwen3:8b`.

Tải model và dựng dữ liệu:

```bash
ollama pull qwen3:4b-instruct   # LLM, 2,5 GB
make models                     # BGE-M3 + reranker + PhoWhisper-small từ Hugging Face
make infra-up                   # chạy Postgres, Qdrant, Redis bằng Docker
make migrate                    # tạo bảng trong Postgres
```

Nạp corpus mẫu — model-server phải chạy để tạo embedding. Mốc dưới đây đặt Luật 2013 hết hiệu lực
ngay trước ngày Luật 2024 có hiệu lực; Luật 43/2024 đã sửa ngày hiệu lực ghi trong bản gốc Luật 31.
Mở **terminal riêng**:

```bash
make dev-models                 # terminal 1, để chạy luôn
```

```bash
make ingest FILE=raw_data/Luật-45-2013-QH13.docx ARGS="--expiry-date 2024-08-01"
make ingest FILE=raw_data/Luật-31-2024-QH15.docx ARGS="--effective-date 2024-08-01"
make ingest FILE=raw_data/Luật-43-2024-QH15.docx ARGS="--effective-date 2024-08-01"
make ingest FILE=raw_data/Nghị-quyết-254-2025-QH15.docx ARGS="--effective-date 2026-01-01"
make docs                       # kiểm tra có đủ bốn văn bản
```

Trước lần nạp đầu, nên xác nhận parser đọc được cả file bằng `--dry-run` (bỏ `--dry-run` để nạp):

```bash
make ingest FILE=raw_data/Luật-45-2013-QH13.docx ARGS="--dry-run --expiry-date 2024-08-01"
make ingest FILE=raw_data/Luật-31-2024-QH15.docx ARGS="--dry-run --effective-date 2024-08-01"
make ingest FILE=raw_data/Luật-43-2024-QH15.docx ARGS="--dry-run --effective-date 2024-08-01"
make ingest FILE=raw_data/Nghị-quyết-254-2025-QH15.docx ARGS="--dry-run --effective-date 2026-01-01"
```

Ngày hết hiệu lực là cận trên không bao gồm: Luật 2013 được giữ để tra cứu lịch sử nhưng không
được tìm như luật đang hiệu lực từ 01/08/2024. Nạp lại cùng file không tạo bản trùng.

## 3. Chạy hằng ngày

Docker và Ollama đang chạy, rồi mỗi lệnh một terminal (terminal nào chạy web phải `nvm use` trước):

```bash
make infra-up                   # nếu container chưa chạy
make dev-models                 # terminal 1 — model-server :8001 (chờ nạp xong model mới hỏi được)
make dev-api                    # terminal 2 — API :8000
nvm use && make dev-web         # terminal 3 — web :3000
```

Mở http://127.0.0.1:3000.

Nút microphone hoặc nút tải file trong ô hỏi dùng PhoWhisper chạy ở `model-server` để chuyển giọng nói
tiếng Việt thành văn bản. File audio tối đa 20 MB; âm thanh được xử lý cục bộ và xóa sau khi nhận dạng.
Bản chữ hiện trong ô nhập để người dùng sửa trước khi gửi câu hỏi. Nút loa dưới câu trả lời dùng giọng đọc tiếng Việt của trình duyệt/hệ điều hành;
nội dung không gửi sang dịch vụ đọc giọng nói bên ngoài. Giọng đọc có sẵn tùy trình duyệt và hệ điều
hành. Lần đầu chạy `make models` tải thêm PhoWhisper-small.

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
Hướng dẫn chuẩn bị thí nghiệm fine-tune và so sánh checkpoint: [`docs/fine-tuning.md`](docs/fine-tuning.md).

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
| `make infra-up` báo cổng 5432/6379 đã dùng | Postgres/Redis cài sẵn trên máy đang chạy — tắt chúng (macOS: `brew services stop postgresql`; Linux/WSL2: `sudo service postgresql stop`) |
| Windows: `make` báo lỗi lạ như `*** missing separator` hoặc `\r` | Repo bị clone với CRLF (ngoài WSL). Clone lại trong WSL; `.gitattributes` ép LF |
| `make dev-web` hoặc `make test` lỗi ở phần web | Node sai bản — chạy `nvm use` trong terminal đó |
| Hỏi bị lỗi, log API báo không tìm thấy model | Chưa `ollama pull` đúng model ghi trong `LLM_MODEL` của `.env`, hoặc Ollama chưa chạy |
| `make ingest` báo không kết nối được model-server | Chưa chạy `make dev-models` |
| Nhập giọng nói báo lỗi nạp model PhoWhisper | Kiểm tra `MS_TRANSCRIBE_MODEL=vinai/PhoWhisper-small` trong `.env`, chạy `make models`, rồi khởi động lại `make dev-models` |
| Mọi câu đều nhận "Không tìm thấy căn cứ trong dữ liệu hiện có…" | Chưa nạp dữ liệu — xem `make docs` |
| `/readyz` trả 503 | Xem thành phần bị lỗi trong JSON trả về và bật lại nó |

## Lưu ý

- Không commit `.env`.
- Câu trả lời chỉ mang tính tham khảo; corpus hiện chưa có đầy đủ nghị định, thông tư, văn bản địa phương
  và các hướng dẫn pháp luật đất đai ban hành sau các văn bản mẫu trong `raw_data/`.
