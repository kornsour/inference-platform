# Phase 2 — Capstone: Autoscaling Inference Platform

**Goal:** build a small but real inference platform on Kubernetes that autoscales on inference-aware signals. This is the heart of the project. It mirrors, at homelab scale, what a production inference platform does at global scale: serve open-weights models on GPUs, scale them on the signals that actually predict saturation, and make the whole thing observable, declarative, and reproducible.

**Status: the core platform is built and validated on real GPUs.** The autoscaling control plane was first validated locally with no GPU on a `kind` cluster, where KEDA scaled the deployment from 1 to 5 replicas on the queue-depth signal, with Grafana dashboards, an SLO, and alerts. The build then moved onto real GPUs: the [DIY two-GPU cluster](gpu-node/diy-cluster.md) is live and serving real vLLM, with cross-node GPU and inference metrics flowing into a single Prometheus. The one core layer still pending live bring-up is the Envoy AI Gateway; the reinforcement items (canary/shadow, a game-day, disaggregated prefill/decode) are tracked as next steps in the checklist below.

**Real-GPU progress on the DIY two-GPU cluster (RTX 3060 Ti + RTX 4070, 8 GB each):**

- :material-check: **Real vLLM serving** on the 8 GB cards (Qwen2.5-1.5B and 3B), with TTFT, throughput, KV-cache, and cost numbers and a 1.5B-vs-3B comparison ([real-gpu-results.md](gpu-node/real-gpu-results.md)). The 3B run reproduces the autoscaler's trigger conditions on real hardware: KV-cache 99.5%, queue depth 12, TTFT p95 4.1s.
- :material-check: **Cross-node networking root-caused and fixed.** The failure was a WSL2 mirrored-mode and kernel-VXLAN-socket limitation, written up as a debugging case study ([troubleshooting log](../docs/cluster-troubleshooting-log.md)).
- :material-check: **Cluster-wide GPU and vLLM telemetry** in Prometheus (hostNetwork exporters plus a vLLM PodMonitor, working around the overlay).
- :material-check: **Two-GPU load-balanced scale-out.** One replica per card behind an external nginx LB, so both GPUs serve in parallel at roughly 2,360 tok/s aggregate.
- :material-check: **KServe InferenceService variant and comparison.** The same model served the platform way (RawDeployment plus the huggingface/vLLM runtime). Serving numbers are identical to the plain Deployment, so KServe's cost is operational, not runtime ([results](gpu-node/real-gpu-results.md), [architecture decisions](architecture-decisions.md)).
- :material-check: **KEDA wired on the real cluster.** A `ScaledObject` autoscales vLLM on queue depth plus KV-cache (the HPA reads `0/3, 0/700m`), not CPU. Prometheus is exposed via hostNetwork so KEDA can reach it across the broken overlay.
- :material-check: **Custom Go KEDA external scaler** that combines KV-cache and queue-depth into one composite trigger ([`keda-inference-scaler/`](keda-inference-scaler/README.md)).
- :material-check: **CI and GitOps.** GitHub Actions validates manifests and builds and tests the Go scaler. Argo CD `Application`s declare the platform ([`gitops/`](../gitops/README.md)).
- :material-check: **One-command bootstrap and teardown** ([`bootstrap/`](../bootstrap/README.md)) that reconstitutes the whole stack, including the WSL2 workarounds, for demos. Argo CD is live on the cluster syncing the platform.
- :material-progress-clock: **Envoy AI Gateway.** Automated in the bootstrap with route manifests written. Live bring-up is the one layer still pending, since it needs helm and is the most overlay-sensitive component.
- :material-check: **Tech-stack rationale.** Every tool and language is justified with its purpose, trade-off, and benefit in [tech-stack.md](tech-stack.md).

- [`local/`](local/) is the runnable local stack (mock vLLM plus KEDA plus Prometheus/Grafana), one command: `make up`
- [`gpu-node/`](gpu-node/README.md) is the DIY two-GPU cluster (two 8 GB consumer GPUs as k3s GPU workers) serving real vLLM at $0, including the [runbook](gpu-node/diy-cluster.md)
- [`gpu-node/real-gpu-results.md`](gpu-node/real-gpu-results.md) has the real-GPU serving numbers: 1.5B vs 3B and the two-GPU load-balanced scale-out
- [`WRITEUP.md`](WRITEUP.md) is the portfolio write-up (local and real-GPU results)
- [`loadtest/`](loadtest/) is the load and capture harness ([`gpu-loadtest.py`](loadtest/gpu-loadtest.py), `scale-demo.sh`, `incluster-load.yaml`)
- [`runbook.md`](runbook.md) is the operational runbook (draft)

## Architecture

```text
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

- [x] Deploy an open-weights model on Kubernetes via **KServe** with **vLLM** as the engine. Done both ways: a [plain Deployment](gpu-node/vllm-plain.yaml) and a [KServe `InferenceService`](gpu-node/kserve-inferenceservice.yaml) (RawDeployment plus the huggingface/vLLM runtime). Numbers and the operational comparison are in [real-gpu-results.md](gpu-node/real-gpu-results.md), and the trade-offs are in [architecture-decisions.md](architecture-decisions.md).
- [x] **Autoscale with KEDA** driven by TTFT p95 or KV-cache utilization from Prometheus, not CPU. Validated locally from 1 to 5 replicas, now live on the GPU cluster as a ScaledObject autoscaling vLLM on queue-depth plus KV-cache (HPA reading `0/3, 0/700m`). See [`k8s/keda-scaledobject.yaml`](k8s/keda-scaledobject.yaml) and [`gpu-node/keda-scaledobject-gpu.yaml`](gpu-node/keda-scaledobject-gpu.yaml). This is the platform's core capability.
- [ ] Add an **inference gateway** (Envoy AI Gateway) for token-aware rate limiting and model routing. Automated in the [bootstrap](../bootstrap/README.md) with route manifests written; live bring-up is pending because it needs helm and is the most overlay-sensitive layer.
- [x] **Instrument everything.** Prometheus scrape plus Grafana dashboards for TTFT, inter-token latency, throughput, queue depth, and GPU utilization. One SLO defined and one alert wired. Done locally (dashboard plus TTFT-p95 SLO plus alerts), and now live on the DIY cluster with cross-node GPU and vLLM metrics in one Prometheus.
- [x] **Load test** and capture saturation behavior. See [`loadtest/`](loadtest/). Captured locally, plus real-GPU load tests on the 2-GPU cluster ([real-gpu-results.md](gpu-node/real-gpu-results.md)).

### Ship real code and treat it like a product platform

- [x] Build at least one genuine code component in a named language: a **custom KEDA external scaler in Go** ([`keda-inference-scaler/`](keda-inference-scaler/README.md)) that scales on a composite KV-cache plus queue-depth signal, which is one trigger the built-in scaler cannot express, plus the [`gpu-loadtest.py`](loadtest/gpu-loadtest.py) harness. Not just YAML.
- [ ] Land **one small PR to an OSS inference project** (vLLM / KServe / KEDA) and link it from the write-up. Submitted to KEDA in [external-scalers#34](https://github.com/kedacore/external-scalers/pull/34) (draft, DCO green), adding the [standalone scaler repo](https://github.com/kornsour/keda-inference-scaler) to the community list.
- [x] **GitOps and CI.** GitHub Actions ([`ci.yml`](../.github/workflows/ci.yml)) lints and schema-validates every manifest and builds and tests the Go scaler. Argo CD `Application`s ([`gitops/`](../gitops/README.md)) declare the platform for continuous reconciliation. A Terraform/Helm IaC pass remains.
- [x] The stack is **CNCF end to end.** KServe, KEDA, Prometheus, and Argo CD are all CNCF projects (Argo CD, KEDA, and Prometheus are graduated).

### Reinforce alongside the build

- [ ] Read disaggregated prefill/decode (NVIDIA Dynamo, llm-d). If budget allows, run prefill and decode on separate pools.
- [ ] Add a **canary or shadow** deployment path so a new model version takes a slice of traffic before full rollout.
- [ ] Write a short `runbook.md` and run one **game-day** failure (kill a pod mid-load). Pair it with a postmortem.

### Milestone

- [ ] A **working demo** I can screen-share: model serving, autoscaling on an inference signal, live dashboards.
- [ ] A **public write-up** ([`WRITEUP.md`](WRITEUP.md)): architecture, load-test results, cost-per-million-tokens, design decisions, next steps.
- [ ] At least **one real code component** in the repo plus **one OSS PR** linked, and the platform **deploys via GitOps/CI/CD** reproducibly from a clean clone.

## Getting a cluster and GPU cheaply

- GPU access on demand: **RunPod**, **Lambda**, or **Modal**. Budget a few hundred dollars for the phase.
- **Shut instances down between sessions.** Idle GPUs are the fastest way to burn the budget, so I treat start/stop discipline as part of the platform's cost model.
- For the control plane without GPU cost, prototype manifests on a local `kind`/`k3d` cluster, then move the workload to a GPU node pool.

> The manifests in [`k8s/`](k8s/) are annotated starting points, not turnkey. Expect to adjust image tags, resource requests, model names, and metric names to match your engine version and cluster. Read the comments.
