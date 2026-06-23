# Local control plane (no GPU)

Build and validate the **autoscaling control loop** on a local `kind` cluster before spending a cent on GPUs. The capstone's hard part is scaling inference on *inference-aware signals* (queue depth, KV-cache utilization) instead of CPU — and that logic can be proven without a real model.

A **metrics-faithful mock** ([`mock-vllm/`](mock-vllm/app.py)) stands in for vLLM: it speaks the OpenAI streaming API and exposes Prometheus metrics with the **exact names a real vLLM emits** (`vllm:num_requests_waiting`, `vllm:gpu_cache_usage_perc`, `vllm:time_to_first_token_seconds`, …). Concurrency is bounded by `CAPACITY` "decode slots"; excess requests queue and register as *waiting*. Because the metric names match, the PodMonitor/ServiceMonitor, KEDA ScaledObject, Prometheus queries, and Grafana panels you build here transfer **unchanged** to the GPU build.

## What this proves

```
locust load ──▶ mock-vllm (Service) ──▶ /metrics (vllm:*)
                     ▲                        │ scraped by
                     │ scales replicas        ▼
                   KEDA ◀──── PromQL ──── Prometheus
                  (queue depth / KV-cache util, NOT CPU)
```

Drive traffic past one replica's capacity → `vllm:num_requests_waiting` rises → KEDA scales the Deployment out → queue drains → after cooldown it scales back in. You *see* the inference-aware autoscaler react, with dashboards, on your laptop.

## Prerequisites

```bash
brew install kind helm kubectl     # cluster tooling
pip install locust                 # load generator
# Docker Desktop must be running (kind runs the cluster in Docker).
```

## Quickstart

```bash
make up                  # kind cluster + KEDA + kube-prometheus-stack + mock deploy
# then, in separate terminals:
make port-forward        # expose the service on localhost:8000
make load                # locust UI at http://localhost:8089 — ramp users up
make watch               # watch replicas scale: deploy/mock-vllm + hpa
make grafana             # dashboards at http://localhost:3000 (admin/admin)
make down                # tear the cluster down when finished
```

Suggested demo: start at 1 replica, ramp locust to ~20 users, and watch `make watch` — the deployment should climb toward `maxReplicaCount` as the queue builds, then settle back after you stop the load.

## Files

| File | Role |
| --- | --- |
| [`mock-vllm/app.py`](mock-vllm/app.py) | OpenAI-compatible mock emitting vLLM-named Prometheus metrics |
| [`kind-config.yaml`](kind-config.yaml) | Single-node local cluster |
| [`manifests/deployment.yaml`](manifests/deployment.yaml) | The mock workload (namespace + Deployment) |
| [`manifests/service.yaml`](manifests/service.yaml) | Service exposing the API + `/metrics` |
| [`manifests/servicemonitor.yaml`](manifests/servicemonitor.yaml) | Prometheus scrape config |
| [`manifests/scaledobject.yaml`](manifests/scaledobject.yaml) | **KEDA ScaledObject — the centerpiece** |
| [`Makefile`](Makefile) | One-command bring-up / teardown |

## Moving to GPU

When the loop works locally, swap the workload for the real thing — the scaling stays identical:

| Local (here) | GPU build ([`../k8s/`](../k8s/)) |
| --- | --- |
| `manifests/deployment.yaml` (mock) | `inferenceservice.yaml` (KServe + vLLM) |
| `manifests/servicemonitor.yaml` | `podmonitor.yaml` |
| `manifests/scaledobject.yaml` | `keda-scaledobject.yaml` (same metrics, same thresholds) |

> **What the mock does not do:** real prefill/decode compute, real GPU memory, or model output. It reproduces the *timing and saturation signals* the control plane reacts to — enough to build and trust the autoscaler, not to measure real cost-per-token. Those numbers come from the GPU run.
