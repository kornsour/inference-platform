#!/usr/bin/env bash
# Formalized autoscaling demo + capture.
#
# Drives streaming load at the inference Service and samples the inference
# signals (queue depth, KV-cache util), the SLI (TTFT p95), and the replica
# count from Prometheus on a fixed cadence — printing a Markdown timeline you
# can paste straight into the write-up. Works against the local mock or a real
# vLLM (same metric names).
#
# Usage:  ./scale-demo.sh            # 72s load, then 30s cooldown observation
#         DURATION=120 ./scale-demo.sh
set -euo pipefail

NS=${NS:-inference}
DURATION=${DURATION:-72}
RPS_SLEEP=${RPS_SLEEP:-0.3}     # ~3.3 req/s
MAXTOK=${MAXTOK:-200}

cleanup() { kill ${PF:-0} ${PROMPF:-0} ${LOAD:-0} 2>/dev/null || true; }
trap cleanup EXIT

kubectl -n "$NS" port-forward svc/mock-vllm 8000:8000 >/tmp/sd-svc.log 2>&1 & PF=$!
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 >/tmp/sd-prom.log 2>&1 & PROMPF=$!
sleep 4

q() {  # query Prometheus for a single scalar value
  curl -s --get http://localhost:9090/api/v1/query --data-urlencode "query=$1" \
    | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(r[0]['value'][1] if r else '0')"
}

# background load: sustained streaming requests for DURATION seconds
( end=$((SECONDS + DURATION)); while [ $SECONDS -lt $end ]; do
    curl -s -m 60 -X POST http://localhost:8000/v1/chat/completions \
      -H 'content-type: application/json' \
      -d "{\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":$MAXTOK,\"stream\":true}" >/dev/null &
    sleep "$RPS_SLEEP"
  done; wait ) & LOAD=$!

echo "| t (s) | waiting | running | KV % | replicas | TTFT p95 (s) |"
echo "| ----: | ------: | ------: | ---: | -------: | -----------: |"
for t in $(seq 0 6 $((DURATION + 30))); do
  printf "| %s | %s | %s | %s | %s | %s |\n" "$t" \
    "$(q 'sum(vllm:num_requests_waiting)')" \
    "$(q 'sum(vllm:num_requests_running)')" \
    "$(q 'max(vllm:gpu_cache_usage_perc)')" \
    "$(q 'sum(kube_deployment_status_replicas{namespace="inference",deployment="mock-vllm"})')" \
    "$(q 'job:vllm_ttft_p95_seconds:5m')"
  sleep 6
done
