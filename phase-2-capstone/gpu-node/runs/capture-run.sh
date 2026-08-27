#!/usr/bin/env bash
# Capture provenance for one real-GPU gpu-loadtest.py run into
# phase-2-capstone/gpu-node/runs/<date>-<run-name>/, per the convention in
# runs/README.md. Run this ON the GPU node (or from a shell with `nvidia-smi`
# and network access to it) alongside the vLLM server you're benchmarking.
#
# It writes command.txt, stdout.log, nvidia-smi.log, vllm-metrics.prom and
# image-digest.txt for one run. It does not start vLLM for you — point it at
# an already-running server.
#
# Usage:
#   ./capture-run.sh --run-name 3b-kv-saturation --image vllm/vllm-openai:v0.6.3 \
#       -- --host 127.0.0.1 --port 8000 --model qwen --base-path /v1 \
#          --concurrency 32 --duration 60 --max-tokens 1500
#
# Everything after `--` is passed straight through to gpu-loadtest.py.
set -euo pipefail

usage() {
  grep '^#' "$0" | cut -c3-
  exit "${1:-0}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOADTEST="$SCRIPT_DIR/../../loadtest/gpu-loadtest.py"

RUN_NAME=""
IMAGE=""
NVIDIA_SMI_INTERVAL=2
LOADTEST_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-name) RUN_NAME="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --nvidia-smi-interval) NVIDIA_SMI_INTERVAL="$2"; shift 2 ;;
    -h|--help) usage 0 ;;
    --) shift; LOADTEST_ARGS=("$@"); break ;;
    *) echo "unknown arg before '--': $1" >&2; usage 1 ;;
  esac
done

[[ -n "$RUN_NAME" ]] || { echo "error: --run-name is required" >&2; usage 1; }
[[ ${#LOADTEST_ARGS[@]} -gt 0 ]] || { echo "error: pass gpu-loadtest.py args after '--'" >&2; usage 1; }

DATE="$(date +%Y-%m-%d)"
RUN_DIR="$SCRIPT_DIR/${DATE}-${RUN_NAME}"
mkdir -p "$RUN_DIR"

# Pull --host/--port out of the passthrough args for the metrics scrape.
HOST="127.0.0.1"
PORT="8000"
for ((i = 0; i < ${#LOADTEST_ARGS[@]}; i++)); do
  case "${LOADTEST_ARGS[$i]}" in
    --host) HOST="${LOADTEST_ARGS[$((i + 1))]}" ;;
    --port) PORT="${LOADTEST_ARGS[$((i + 1))]}" ;;
  esac
done

{
  echo "python3 gpu-loadtest.py ${LOADTEST_ARGS[*]}"
  echo "captured: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$RUN_DIR/command.txt"

if [[ -n "$IMAGE" ]]; then
  {
    docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE" 2>/dev/null \
      || echo "# could not resolve digest for $IMAGE locally — record it manually"
  } > "$RUN_DIR/image-digest.txt"
else
  echo "# no --image given — record the vLLM image digest manually" > "$RUN_DIR/image-digest.txt"
fi

# Sample nvidia-smi in the background for the duration of the load test.
if command -v nvidia-smi >/dev/null 2>&1; then
  (
    while true; do
      date -u +%Y-%m-%dT%H:%M:%SZ
      nvidia-smi
      echo "----"
      sleep "$NVIDIA_SMI_INTERVAL"
    done
  ) > "$RUN_DIR/nvidia-smi.log" &
  SMI_PID=$!
else
  echo "warning: nvidia-smi not found on this host; nvidia-smi.log will be empty" >&2
  SMI_PID=""
fi

set +e
python3 "$LOADTEST" "${LOADTEST_ARGS[@]}" | tee "$RUN_DIR/stdout.log"
LOADTEST_STATUS=$?
set -e

# Scrape /metrics right after the run, while it's still near peak.
if command -v curl >/dev/null 2>&1; then
  curl -sS "http://${HOST}:${PORT}/metrics" > "$RUN_DIR/vllm-metrics.prom" \
    || echo "# curl http://${HOST}:${PORT}/metrics failed — capture manually" > "$RUN_DIR/vllm-metrics.prom"
fi

if [[ -n "$SMI_PID" ]]; then
  kill "$SMI_PID" 2>/dev/null || true
  wait "$SMI_PID" 2>/dev/null || true
fi

echo "captured run: $RUN_DIR"
echo "next: add $RUN_DIR/README.md summarizing the run, then link the date + directory"
echo "      from the matching table caption in ../real-gpu-results.md"
exit "$LOADTEST_STATUS"
