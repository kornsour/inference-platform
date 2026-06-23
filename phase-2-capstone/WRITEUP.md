# Building an autoscaling LLM inference platform on Kubernetes

> **Status: draft.** The control plane is built and validated end-to-end on a
> local cluster; the real-GPU serving numbers (marked _TODO: GPU_) come from the
> single-GPU run described in [`gpu-node/`](gpu-node/README.md).

## TL;DR

I built a Kubernetes platform that autoscales LLM inference on **inference-aware
signals** — request-queue depth and KV-cache utilization — instead of CPU, and
validated the whole control loop locally with **no GPU spend** using a metrics-
faithful mock of vLLM. Under load, KEDA scaled the serving deployment **1 → 5
replicas** on the queue-depth signal, and a load-balanced in-cluster test showed
the new replicas absorbing traffic (concurrent in-flight requests rising to 5×
the single-replica capacity). The non-obvious lesson: the autoscaler is only
half the system — **how traffic is routed to the new replicas decides whether
scaling actually helps.**

## Why inference autoscaling is different

Classic web autoscaling watches CPU and request rate. Both are nearly useless
for LLM serving on a GPU:

- **GPU "utilization %" doesn't track saturation.** It measures the fraction of
  time a kernel was active; a single memory-bound decode can read ~100% while
  real compute headroom is large.
- **Memory-used is pre-allocated.** vLLM reserves most of VRAM for the KV-cache
  pool at startup, so memory-used is pegged regardless of load.

The signals that *do* track saturation are **KV-cache utilization** (the memory
pressure that caps concurrency during decode) and **request-queue depth** (the
leading indicator that TTFT is about to breach its SLO). Those are what this
platform scales on.

## Architecture

```text
 load ─▶ Service (ClusterIP, load-balances) ─▶ vLLM pods ─▶ /metrics (vllm:*)
                         ▲                                       │ scraped by
                         │ scales replicas                       ▼
                       KEDA ◀──────── PromQL ──────────────── Prometheus
                      (queue depth / KV-cache util, NOT CPU)        │
                                                                    ▼
                                                          Grafana + Alerts
```

- **Serving:** KServe + vLLM on a GPU node pool ([`k8s/inferenceservice.yaml`](k8s/inferenceservice.yaml)).
  Locally, a [metrics-faithful mock](local/mock-vllm/app.py) stands in.
- **Autoscaling:** KEDA `ScaledObject` reading Prometheus ([`k8s/keda-scaledobject.yaml`](k8s/keda-scaledobject.yaml)).
- **Observability:** Prometheus scrape + Grafana dashboard + an SLO and alert
  ([`local/manifests/slo-prometheusrule.yaml`](local/manifests/slo-prometheusrule.yaml)).

## Autoscaling on an inference-aware signal

The [`ScaledObject`](local/manifests/scaledobject.yaml) defines two Prometheus
triggers — `sum(vllm:num_requests_waiting) > 3` and
`max(vllm:gpu_cache_usage_perc) > 0.7` — over a 1–5 replica range. KEDA
synthesizes an HPA from these external metrics; no CPU target anywhere.

## Load test & results (local, mock engine)

Single-node `kind` cluster, mock vLLM with 4 "decode slots" per replica,
`min=1 max=5`. Driving ~3.3 streaming req/s of 200-token responses:

| t (s) | queue (waiting) | replicas | event |
| ----: | --------------: | -------: | --- |
| 0  | 0   | 1 | idle |
| 12 | 30  | 1 | one replica saturated, queue building |
| 24 | 61  | **5** | KEDA scaled out (queue ≫ threshold 3) |
| 72 | 203 | 5 | still backlogged at max replicas |

`SuccessfulRescale … reason: external metric s0-prometheus … above target` — the
autoscaler reacted to the **queue-depth** signal, exactly as designed. TTFT p95
pegged the top histogram bucket (well over the 1 s SLO), firing
`InferenceTTFTSLOBreach`.

**Routing matters as much as scaling.** The first run drove traffic via
`kubectl port-forward`, which pins to a *single* pod — so the four new replicas
sat idle and the queue kept growing despite the scale-out. Re-running with a
**load-balanced in-cluster generator** ([`loadtest/incluster-load.yaml`](loadtest/incluster-load.yaml))
against the ClusterIP, in-flight requests climbed to **20 (= 5 replicas × 4
slots)** — the new capacity was actually used. This is the case for the
inference gateway: scaling is worthless if the front door doesn't spread load.

**Capacity-planning takeaway.** At `max=5 × 4 slots = 20` concurrent and ~30
offered, the queue never fully drained — the platform was simply under-
provisioned for that load. The levers: raise `maxReplicas`, raise per-replica
concurrency (KV-cache headroom / quantization), or shed/queue with backpressure.

## Real-GPU serving numbers

_TODO: GPU._ Run real vLLM on the single 12 GB GPU node (see
[`gpu-node/`](gpu-node/README.md)) and record, for a small quantized model:

| metric | value |
| --- | --- |
| Model / quantization | _TODO_ |
| TTFT p50 / p95 @ 1 replica | _TODO_ |
| Sustained throughput (tok/s) | _TODO_ |
| KV-cache blocks / max concurrency | _TODO_ |
| Cost-per-million-tokens (amortized) | _TODO_ |

> A single consumer GPU validates *real* vLLM serving (PagedAttention,
> continuous batching, true KV-cache metrics) but cannot demonstrate multi-
> replica GPU scale-out — that needs ≥2 GPUs. The control loop above already
> proves the scaling behavior; the GPU run proves the engine behavior. Same
> metric names tie them together.

## Design decisions

- **KEDA over the KServe/Knative autoscaler** — to scale on arbitrary Prometheus
  metrics (queue depth, KV-cache) rather than concurrency/RPS alone.
- **Mock-first** — validate the control plane for $0 before paying for GPUs;
  the metric names are identical, so nothing changes when vLLM replaces the mock.
- **One SLO, one alert** — TTFT p95 < 1 s, alert on sustained breach. Keep the
  signal sharp rather than dashboarding everything.

## What's next

- Inference gateway (Envoy AI Gateway) for token-aware routing + rate limiting.
- GitOps (Argo CD) + CI to lint/validate manifests on every change.
- The GPU serving run to fill the numbers above.
