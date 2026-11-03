# Embedding + rerank service (BGE-M3, bge-reranker-v2-m3). Linux torch wheels bundle CUDA,
# so the same image runs on GPU (nvidia container toolkit) or CPU.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/models/hf \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8001
CMD ["uvicorn", "model_server.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8001"]
