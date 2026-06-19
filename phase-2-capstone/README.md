# Phase 2 — Hands-On Platform Build (Months 3–4)

**Goal:** convert literacy into demonstrable capability by building a small but real inference platform on Kubernetes that **autoscales on inference-aware signals**. This is the heart of the project and the spine of the technical interview track. Mirror, at small scale, what the target role operates at global scale.

This is also where existing EKS / GitOps / Prometheus skills give a large head start over candidates who know models but not platforms. Lead with that.

## Architecture

```
                    ┌──────────────────────┐
   client traffic → │  Envoy AI Gateway     │  token-aware rate limiting, model routing
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  KServe               │  LLMInferenceService
                    │  InferenceService     │  (vLLM runtime, OpenAI-compatible)
                    └──────────┬───────────┘
                               │ exposes /metrics (TTFT, KV-cache %, queue depth)
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
        ┌──────────┐    ┌─────────────┐   ┌──────────────┐
        │Prometheus│───▶│ KEDA         │   │ Grafana       │
        │          │    │ ScaledObject │   │ dashboards    │
        └──────────┘    └──────┬──────┘   └──────────────┘
                               │ scales replicas on TTFT p95 / KV-cache util
                               ▼
                        GPU-backed pods
```

## Checklist

### Build
- [ ] Deploy an open-weights model on Kubernetes via **KServe** (or Ray Serve) with **vLLM** as the engine — see [`k8s/inferenceservice.yaml`](k8s/inferenceservice.yaml).
- [ ] **Autoscale with KEDA** driven by TTFT p95 or KV-cache utilization from Prometheus, **not CPU** — see [`k8s/keda-scaledobject.yaml`](k8s/keda-scaledobject.yaml). *This is the single most important thing to get working.*
- [ ] Add an **inference gateway** (Envoy AI Gateway) for token-aware rate limiting and model routing.
- [ ] **Instrument everything**: Prometheus scrape ([`k8s/podmonitor.yaml`](k8s/podmonitor.yaml)) + Grafana dashboards for TTFT, inter-token latency, throughput, queue depth, GPU utilization. Define one SLO and wire one alert.
- [ ] **Load test** and capture saturation behavior — see [`loadtest/locustfile.py`](loadtest/locustfile.py).

### Ship real code + treat it like a product platform (Staff EM credibility)
- [ ] Build at least one genuine code component in a **named language** — a token-aware router or **custom KEDA external scaler in Go**, or extend the Python benchmark harness. Not just YAML.
- [ ] Land **one small PR to an OSS inference project** (vLLM / KServe / KEDA) and link it from the write-up.
- [ ] **GitOps** (Argo CD or Flux) for declarative deploys; **CI/CD** (lint → test → build → deploy preview); **IaC** (Terraform or Helm); an automated **smoke/integration test** after each deploy. → *"engineering excellence through automation, tooling, and standardization across deployment, testing, and operations."*
- [ ] Note in the write-up that the stack (KServe, KEDA, Prometheus, Envoy) is **CNCF** — a preferred qualification you can claim.

### Reinforce alongside the build
- [ ] Read disaggregated prefill/decode (NVIDIA Dynamo, llm-d). If budget allows, run prefill and decode on separate pools.
- [ ] Add a **canary or shadow** deployment path so a new model version takes a slice of traffic before full rollout.
- [ ] Write a short [`runbook.md`](runbook-template.md) and run one **game-day** failure (kill a pod mid-load). Pair with a postmortem.

### Milestone
- [ ] A **working demo** you can screen-share: model serving, autoscaling on an inference signal, live dashboards.
- [ ] A **public write-up** — fill in [`WRITEUP-template.md`](WRITEUP-template.md): architecture, load-test results, cost-per-million-tokens, design decisions, next steps.
- [ ] At least **one real code component** in the repo + **one OSS PR** linked, and the platform **deploys via GitOps/CI/CD** reproducibly from a clean clone.

## Getting a cluster + GPU cheaply

- GPU access on demand: **RunPod**, **Lambda**, or **Modal**. Budget a few hundred dollars for the phase.
- **Shut instances down between sessions** — the same scheduling/cost discipline that delivered the 6% compute reduction at GE. Make that discipline part of the story.
- For the control plane without GPU cost, you can prototype manifests on a local `kind`/`k3d` cluster, then move the workload to a GPU node pool.

> The manifests in [`k8s/`](k8s/) are annotated starting points, not turnkey. Expect to adjust image tags, resource requests, model names, and metric names to match your engine version and cluster. Read the comments.
