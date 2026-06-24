# Phase 2 — Hands-On Platform Build (Months 3–4)

**Goal:** convert literacy into demonstrable capability by building a small but real inference platform on Kubernetes that **autoscales on inference-aware signals**. This is the heart of the project and the spine of the technical interview track. Mirror, at small scale, what the target role operates at global scale.

This is also where existing EKS / GitOps / Prometheus skills give a large head start over candidates who know models but not platforms. Lead with that.

**Status: In progress.** The autoscaling control plane is **built and validated locally** (no GPU) on a `kind` cluster — KEDA scaled the deployment 1→5 on the queue-depth signal, with Grafana dashboards, an SLO, and alerts. The build has since moved onto **real GPUs**: the [DIY two-GPU cluster](gpu-node/diy-cluster.md) is live and serving **real vLLM**, with cross-node GPU + inference metrics flowing into a single Prometheus.

**Real-GPU progress — DIY two-GPU cluster (RTX 3060 Ti + RTX 4070, 8 GB each):**

- :material-check: **Real vLLM serving** on the 8 GB cards — Qwen2.5-1.5B and 3B, with TTFT / throughput / KV-cache / cost numbers and a 1.5B-vs-3B comparison ([real-gpu-results.md](gpu-node/real-gpu-results.md)). The 3B run reproduces the autoscaler's trigger conditions on real hardware (KV-cache 99.5 %, queue depth 12, TTFT p95 4.1 s).
- :material-check: **Cross-node networking root-caused & fixed** — a WSL2 mirrored-mode / kernel-VXLAN-socket limitation; written up as a debugging case study ([troubleshooting log](../docs/cluster-troubleshooting-log.md)). Real platform-debugging evidence.
- :material-check: **Cluster-wide GPU + vLLM telemetry** in Prometheus (hostNetwork exporters + a vLLM PodMonitor, working around the overlay).
- :material-check: **Two-GPU load-balanced scale-out** — one replica per card behind an external nginx LB; both GPUs serve in parallel (~2,360 tok/s aggregate).
- :material-check: **KServe InferenceService** variant + comparison — same model the platform way (RawDeployment + huggingface/vLLM runtime); serving numbers identical to the plain Deployment, so KServe's cost is **operational, not runtime** ([results](gpu-node/real-gpu-results.md), [architecture decisions](architecture-decisions.md)).
- :material-check: **KEDA wired on the real cluster** — a `ScaledObject` autoscaling vLLM on **queue depth + KV-cache** (the HPA reads `0/3, 0/700m`), not CPU. Prometheus exposed via hostNetwork so KEDA can reach it across the broken overlay.
- :material-check: **Custom Go KEDA external scaler** — composite KV-cache + queue-depth signal in one trigger ([`keda-inference-scaler/`](keda-inference-scaler/README.md)).
- :material-check: **CI + GitOps** — GitHub Actions validates manifests + builds/tests the Go scaler; Argo CD `Application`s declare the platform ([`gitops/`](../gitops/README.md)).
- :material-progress-clock: **OSS PR** — prepared and ready to submit ([oss-contribution.md](oss-contribution.md)); submitting is yours to do.
- :material-check: **One-command bootstrap / teardown** ([`bootstrap/`](../bootstrap/README.md)) — reconstitutes the whole stack (incl. the WSL2 workarounds) for demos; **Argo CD is live** on the cluster syncing the platform.
- :material-progress-clock: **Envoy AI Gateway** — automated in the bootstrap + route manifests written; live bring-up is the one layer still pending (needs helm; it's the most overlay-sensitive).
- :material-check: **Tech-stack rationale** — every tool + language justified (why / trade-off / benefit) in [tech-stack.md](tech-stack.md).

- [`local/`](local/) — the runnable local stack (mock vLLM + KEDA + Prometheus/Grafana), one command: `make up`
- [`gpu-node/`](gpu-node/README.md) — the **DIY two-GPU cluster** (two 8 GB consumer GPUs as k3s GPU workers) serving real vLLM at $0, incl. the [runbook](gpu-node/diy-cluster.md)
- [`gpu-node/real-gpu-results.md`](gpu-node/real-gpu-results.md) — **real-GPU serving numbers**: 1.5B vs 3B and the two-GPU load-balanced scale-out
- [`WRITEUP.md`](WRITEUP.md) — portfolio write-up (local + real-GPU results in)
- [`loadtest/`](loadtest/) — load + capture harness ([`gpu-loadtest.py`](loadtest/gpu-loadtest.py), `scale-demo.sh`, `incluster-load.yaml`)
- [`runbook.md`](runbook.md) — operational runbook (draft)

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

- [x] Deploy an open-weights model on Kubernetes via **KServe** with **vLLM** as the engine — done both ways: a [plain Deployment](gpu-node/vllm-plain.yaml) *and* a [KServe `InferenceService`](gpu-node/kserve-inferenceservice.yaml) (RawDeployment + huggingface/vLLM runtime). Numbers + the operational comparison in [real-gpu-results.md](gpu-node/real-gpu-results.md); trade-offs in [architecture-decisions.md](architecture-decisions.md).
- [x] **Autoscale with KEDA** driven by TTFT p95 or KV-cache utilization from Prometheus, **not CPU** *(validated locally 1→5; now **live on the GPU cluster** — a ScaledObject autoscaling vLLM on queue-depth + KV-cache, HPA reading `0/3, 0/700m`, not CPU)* — see [`k8s/keda-scaledobject.yaml`](k8s/keda-scaledobject.yaml) and [`gpu-node/keda-scaledobject-gpu.yaml`](gpu-node/keda-scaledobject-gpu.yaml). *This is the single most important thing to get working.*
- [ ] Add an **inference gateway** (Envoy AI Gateway) for token-aware rate limiting and model routing. *(automated in the [bootstrap](../bootstrap/README.md) with route manifests written; live bring-up pending — needs helm and it's the most overlay-sensitive layer.)*
- [x] **Instrument everything**: Prometheus scrape + Grafana dashboards for TTFT, inter-token latency, throughput, queue depth, GPU utilization. Define one SLO and wire one alert. *(done locally; dashboard + TTFT-p95 SLO + alerts — and now live on the DIY cluster: cross-node GPU + vLLM metrics in one Prometheus)*
- [x] **Load test** and capture saturation behavior — see [`loadtest/`](loadtest/). *(captured locally; plus real-GPU load tests on the 2-GPU cluster — [real-gpu-results.md](gpu-node/real-gpu-results.md))*

### Ship real code + treat it like a product platform (Staff EM credibility)

- [x] Build at least one genuine code component in a **named language** — a **custom KEDA external scaler in Go** ([`keda-inference-scaler/`](keda-inference-scaler/README.md)) that scales on a *composite* KV-cache + queue-depth signal (one trigger the built-in scaler can't express), plus the [`gpu-loadtest.py`](loadtest/gpu-loadtest.py) harness. Not just YAML.
- [ ] Land **one small PR to an OSS inference project** (vLLM / KServe / KEDA) and link it from the write-up. *(prepared & ready to submit — [oss-contribution.md](oss-contribution.md); the actual PR is a manual step under your GitHub identity.)*
- [x] **GitOps + CI** — GitHub Actions ([`ci.yml`](../.github/workflows/ci.yml)) lints/schema-validates every manifest and builds + tests the Go scaler; Argo CD `Application`s ([`gitops/`](../gitops/README.md)) declare the platform for continuous reconciliation. *(Argo CD install on the DIY cluster + a Terraform/Helm IaC pass remain.)* → *"engineering excellence through automation, tooling, and standardization."*
- [x] The stack is **CNCF** — KServe, KEDA, Prometheus, and Argo CD are all CNCF projects (Argo is graduated; KEDA graduated; Prometheus graduated) — a preferred qualification to claim.

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
