#!/usr/bin/env bash
# Run on a container-type GPU host (Vast.ai, RunPod...) where docker compose is unavailable.
# Starts Ollama (:11434) and model-server (:8001), both bound to 127.0.0.1 (no auth: use an SSH tunnel).
#
#   git clone <repo> /workspace/chatbot-law && cd /workspace/chatbot-law
#   bash deploy/vast-setup.sh          # idempotent: safe to re-run after a restart
#
# Env: OLLAMA_PULL="qwen3:8b" (space-separated), OLLAMA_NUM_PARALLEL=4, MS_DEVICE=auto
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${DATA_DIR:-/workspace}"
LOGS="$DATA/logs"
OLLAMA_PULL="${OLLAMA_PULL:-qwen3:8b}"
mkdir -p "$LOGS" "$DATA/ollama" "$DATA/hf"

command -v nvidia-smi >/dev/null || { echo "nvidia-smi not found: this host has no GPU driver" >&2; exit 1; }
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# --- tools ---
if ! command -v curl >/dev/null || ! command -v zstd >/dev/null; then
  apt-get update -qq && apt-get install -y -qq curl zstd ca-certificates
fi
command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# --- ollama ---
export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS="$DATA/ollama" OLLAMA_KEEP_ALIVE=24h \
       OLLAMA_FLASH_ATTENTION=1 OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-4}"
if ! curl -fs http://127.0.0.1:11434/api/tags >/dev/null; then
  nohup ollama serve >"$LOGS/ollama.log" 2>&1 &
  until curl -fs http://127.0.0.1:11434/api/tags >/dev/null; do sleep 1; done
fi
for m in $OLLAMA_PULL; do ollama pull "$m"; done

# --- model-server ---
export HF_HOME="$DATA/hf" MS_DEVICE="${MS_DEVICE:-auto}"
cd "$ROOT/model-server"
uv sync --frozen --no-dev
if ! curl -fs http://127.0.0.1:8001/healthz >/dev/null; then
  nohup uv run --no-dev uvicorn model_server.main:app_factory --factory \
    --host 127.0.0.1 --port 8001 >"$LOGS/model-server.log" 2>&1 &
fi

echo "Waiting for model-server to load BGE-M3 (first run downloads ~6 GB)..."
until curl -fs http://127.0.0.1:8001/healthz >/dev/null; do sleep 5; done
echo "READY  ollama: $(curl -s http://127.0.0.1:11434/api/tags | head -c 120)"
echo "       model-server: $(curl -s http://127.0.0.1:8001/healthz)"
echo "Logs: $LOGS/{ollama,model-server}.log"
