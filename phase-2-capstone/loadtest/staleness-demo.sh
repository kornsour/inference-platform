#!/usr/bin/env bash
# Reproduces one signal-staleness regime against the metrics-faithful mock:
# sets the local ScaledObject's pollingInterval, drives a step-function load
# (idle -> sustained burst -> stop), and samples queue depth, KV-cache %, and
# replica count from Prometheus at a tight cadence so the resulting timeline
# shows whether replicas step cleanly with the queue or lag/oscillate behind
# it. See docs/autoscaling-signal-staleness.md for what the three regimes are
# and why POLLING_INTERVAL is the variable that matters.
#
# Usage:
#   POLLING_INTERVAL=3  ./staleness-demo.sh   # well below the 10s scrape interval
#   POLLING_INTERVAL=10 ./staleness-demo.sh   # equal to it
#   POLLING_INTERVAL=30 ./staleness-demo.sh   # well above it (KEDA's own default)
#
# Requires the local stack up (`cd ../local && make up`) with a mostly-idle
# mock-vllm (1 replica) before starting, so each run is a clean step function
# rather than picking up mid-scale-out from a previous one.
set -euo pipefail

NS=${NS:-inference}
POLLING_INTERVAL=${POLLING_INTERVAL:?set POLLING_INTERVAL (seconds) -- see usage above}
SCALEDOBJECT=${SCALEDOBJECT:-mock-vllm-scaler}
DEPLOYMENT=${DEPLOYMENT:-mock-vllm}
DURATION=${DURATION:-90}        # seconds of sustained load
COOLDOWN=${COOLDOWN:-60}        # seconds observed after load stops
SAMPLE_INTERVAL=${SAMPLE_INTERVAL:-2}
RPS_SLEEP=${RPS_SLEEP:-0.15}    # faster ramp than scale-demo.sh: shorter total run
MAXTOK=${MAXTOK:-200}

cleanup() { kill "${PF:-0}" "${PROMPF:-0}" "${LOAD:-0}" 2>/dev/null || true; }
trap cleanup EXIT

echo "# staleness regime: pollingInterval=${POLLING_INTERVAL}s" >&2
kubectl -n "$NS" patch scaledobject "$SCALEDOBJECT" --type merge \
  -p "{\"spec\":{\"pollingInterval\":${POLLING_INTERVAL}}}" >&2

replicas() { kubectl -n "$NS" get deploy "$DEPLOYMENT" -o jsonpath='{.status.replicas}' 2>/dev/null || echo 0; }
echo "waiting for a clean baseline (1 replica) before starting..." >&2
for _ in $(seq 1 30); do
  [ "$(replicas)" = "1" ] && break
  sleep 2
done

kubectl -n "$NS" port-forward svc/mock-vllm 8000:8000 >/tmp/sld-svc.log 2>&1 & PF=$!
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 >/tmp/sld-prom.log 2>&1 & PROMPF=$!
sleep 4

q() {  # query Prometheus for a single scalar value
  curl -s --get http://localhost:9090/api/v1/query --data-urlencode "query=$1" \
    | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(r[0]['value'][1] if r else '0')"
}

# step-function load: nothing until t=0 (already idle above), then a sustained
# burst for DURATION seconds, then nothing -- the step this regime's lag
# chain has to react to in both directions.
( end=$((SECONDS + DURATION)); while [ $SECONDS -lt $end ]; do
    curl -s -m 60 -X POST http://localhost:8000/v1/chat/completions \
      -H 'content-type: application/json' \
      -d "{\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":$MAXTOK,\"stream\":true}" >/dev/null &
    sleep "$RPS_SLEEP"
  done; wait ) & LOAD=$!

echo "regime: pollingInterval=${POLLING_INTERVAL}s"
echo "| t (s) | waiting | KV % | replicas |"
echo "| ----: | ------: | ---: | -------: |"
for t in $(seq 0 "$SAMPLE_INTERVAL" $((DURATION + COOLDOWN))); do
  printf "| %s | %s | %s | %s |\n" "$t" \
    "$(q 'sum(vllm:num_requests_waiting)')" \
    "$(q 'max(vllm:gpu_cache_usage_perc)')" \
    "$(q "sum(kube_deployment_status_replicas{namespace=\"$NS\",deployment=\"$DEPLOYMENT\"})")"
  sleep "$SAMPLE_INTERVAL"
done
