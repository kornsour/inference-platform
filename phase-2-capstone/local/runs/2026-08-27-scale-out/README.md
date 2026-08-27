# Scale-out demo run — 2026-08-27

Raw evidence for the local KEDA scale-out result quoted in
[`../../../WRITEUP.md`](../../../WRITEUP.md) ("Load test and results (local, mock
engine)"). This directory captures one execution of `scale-demo.sh` end to
end, so the 1 → 5 replica timeline is reproducible rather than transcribed
by hand.

## Cluster

- **Kind cluster:** `inference-platform` (Kubernetes v1.36.1, kind node image `v1.36.1`), brought up via `phase-2-capstone/local/Makefile`'s `make up` (kind + KEDA + kube-prometheus-stack + the mock-vLLM deployment).
- **Workload:** `local/mock-vllm` (metrics-faithful mock, not a real GPU/model) — image `mock-vllm:local`, `CAPACITY=4` decode slots/replica, `min=1 max=5` (`local/manifests/scaledobject.yaml`).
- No GPU involved. This is the local, $0 control-loop validation; the GPU-side numbers live under `../../../gpu-node/` (see the top-level `phase-2-capstone/README.md` for which surface each number belongs to).

## Exact command

```bash
cd phase-2-capstone/loadtest
NS=inference DURATION=90 RPS_SLEEP=0.3 MAXTOK=200 ./scale-demo.sh
```

Run start: 2026-08-27 17:43 UTC (13:43 EDT). ~3.3 req/s of 200-token streaming
requests sustained for 90s, then observed through cooldown per the script's
own loop (`DURATION + 30` seconds of sampling at a 6s cadence).

## Files

| File | What it is |
| --- | --- |
| [`scale-demo-output.md`](scale-demo-output.md) | Raw stdout of the run above — the Markdown timeline table `scale-demo.sh` prints (queue depth, running requests, KV-cache %, replica count, TTFT p95), sampled from Prometheus every 6s. |
| [`events-successfulrescale.yaml`](events-successfulrescale.yaml) | `kubectl -n inference get events --field-selector reason=SuccessfulRescale -o yaml`, captured right after the run while the `SuccessfulRescale` event was still in the namespace's event window. |
| [`describe-hpa-peak.txt`](describe-hpa-peak.txt) | `kubectl -n inference describe hpa`, captured at peak (5/5 replicas, `ScalingLimited: TooManyReplicas`). |

## What it shows

Replica count jumps from 1 to 5 at t=36s once `sum(vllm:num_requests_waiting)`
clears the ScaledObject's threshold (3) — the same queue-depth trigger
documented in `WRITEUP.md`. The queue keeps growing even after scale-out
(97 → 249 waiting) because offered load (~3.3 req/s of 200-token generations)
exceeds `5 replicas × 4 slots` capacity for the duration of this run — this
run did not use the load-balanced in-cluster generator
(`loadtest/incluster-load.yaml`) called out in `WRITEUP.md`'s "Routing
matters" note, so traffic here still went through a single `port-forward`
connection as `scale-demo.sh` drives it. TTFT p95 accordingly pegs at
9.5–10s rather than recovering; that is expected for this script/traffic
shape and is why the write-up's routing caveat exists.

## Reproducing

```bash
cd phase-2-capstone/local && make up      # if the cluster isn't already running
cd ../loadtest
NS=inference DURATION=90 RPS_SLEEP=0.3 MAXTOK=200 ./scale-demo.sh | tee output.md

# right after, from another terminal, while replicas are still scaled out:
kubectl -n inference get events --field-selector reason=SuccessfulRescale -o yaml
kubectl -n inference describe hpa
```
