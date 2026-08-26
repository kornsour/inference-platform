# Inference Platform

> An autoscaling **LLM inference platform on Kubernetes** that scales vLLM on
> inference-aware signals — request-queue depth and KV-cache utilization, not CPU —
> through a custom KEDA external scaler, validated on a DIY two-GPU cluster with
> real vLLM serving.

**Docs site:** <https://kornsour.github.io/inference-platform/> · **Capstone write-up:** [`phase-2-capstone/WRITEUP.md`](phase-2-capstone/WRITEUP.md)

## What I built

- A Kubernetes platform that **autoscales LLM serving on inference-aware signals** —
  request-queue depth and KV-cache utilization — via a **custom Go KEDA external
  scaler** ([`keda-inference-scaler/`](phase-2-capstone/keda-inference-scaler/)) that
  exposes one composite saturation metric. Built and unit-tested in CI.
- **Mock-first, then real GPUs.** The whole control loop is validated for $0 with a
  metrics-faithful vLLM mock (identical `vllm:*` metric names), then the same trigger
  is reproduced on a **DIY two-GPU cluster** running real vLLM (PagedAttention,
  continuous batching, true KV-cache metrics).

![Architecture](docs/img/architecture.svg)

### Headline results — [full write-up](phase-2-capstone/WRITEUP.md)

- **Autoscaling reacts to the right signal.** Under load, KEDA scaled the serving
  Deployment **1 → 5 replicas** on queue depth; a load-balanced generator then put the
  new replicas to work — the non-obvious lesson being that *routing matters as much as
  scaling* (a `port-forward` pins one pod and starves the scale-out).
- **Real two-GPU vLLM.** Qwen2.5-1.5B sustains **~2,600 tok/s** and stays compute-bound
  (never trips the autoscaler); the 3B model's 8.5× smaller KV pool **does** trip the
  KV-cache/queue trigger — the regime flip that motivates inference-aware scaling. Two
  8 GB cards load-balanced to **~2,360 tok/s** aggregate; energy cost
  **~$0.0015–0.005 / 1M tokens**.
- **KServe vs a plain Deployment.** Same engine, same throughput — KServe's cost is
  **operational, not runtime**.

![KEDA scale-out under load](docs/img/scale-out.svg)

> **Companion repo.** This is the **platform / SRE-leaning** side — how you *operate*
> serving at scale (autoscaling, GitOps, observability, cost/SLOs). For the **low-level
> performance-engineering** counterpart — latency/throughput/memory benchmarking and
> kernel/KV-cache/batching/quantization work with before/after numbers — see
> **[`llm-inference-performance`](https://github.com/kornsour/llm-inference-performance)**.

## About this project

Built as self-directed, hands-on depth in LLM inference serving — the platform layer
underneath generative AI models: GPU scheduling, high-throughput serving engines,
inference-aware autoscaling, and the observability and economics of running models at
scale. The two phases below record the path from foundations to the capstone build.

## What is AI inference?

**Inference** is the *serving* phase of a model's lifecycle — taking an already-trained model and running it to produce outputs in response to live requests. It's the counterpart to training: training builds the model's weights; inference *uses* those weights to generate tokens for users. Every time you send a prompt to a chatbot, a coding assistant, or any generative AI product, you are triggering an inference request.

For a large language model, a single request runs in two distinct phases:

- **Prefill** — the first forward pass that processes the entire input prompt and produces the first output token. It is **compute-bound**: work scales with prompt length and saturates GPU compute (FLOPs).
- **Decode** — the token-by-token generation that follows. It is **memory-bandwidth-bound**: each new token depends on the growing KV cache rather than raw compute.

"AI inference" in this repo specifically means **LLM inference serving** — the platform layer underneath generative AI models: GPU scheduling, high-throughput serving engines, inference-aware autoscaling, and the observability and economics of running models at scale.

### Why it matters

- **It's where the cost lives.** A model is trained once but served billions of times. Accelerators (GPUs) are the dominant cost, so the unit economic that matters is **cost-per-million-tokens** — driven by utilization, batching, and quantization. Small efficiency gains compound across every request.
- **It's where the user experience lives.** Latency signals like **time-to-first-token (TTFT)** and tokens-per-second directly shape how a product feels. The serving layer, not the model weights, determines whether responses feel instant or sluggish.
- **It scales differently from normal infrastructure.** CPU utilization is nearly meaningless for GPU inference; the real saturation signals are KV-cache pressure, queue depth, and tail latency. This requires **inference-aware autoscaling** rather than the CPU-based autoscaling most platforms use.
- **It's the fastest-growing layer of the AI stack.** As generative AI moves from demos to production, the platform that serves models efficiently, reliably, and cheaply becomes the bottleneck — and the differentiator.

The [`docs/glossary.md`](docs/glossary.md) breaks down the full vocabulary; this section is the one-paragraph version.

## Why this exists

Most of the platform discipline this domain demands (Kubernetes, GitOps, observability, SLOs, multi-tenant platforms, capacity/cost discipline) transfers directly from general platform engineering. Generative AI *serving* infrastructure specifically — GPU scheduling, inference-aware autoscaling, the engine layer — is a real, distinct skill set. This repo builds that depth by doing, not just reading: standing up real inference endpoints, then a real autoscaling platform on Kubernetes, and writing up the results.

## Structure

| Phase | Theme | Folder |
| --- | --- | --- |
| **1** | Inference serving foundations — vocabulary, economics, first local serve | [`phase-1-foundations/`](phase-1-foundations/) |
| **2** | Hands-on platform build — the capstone: autoscaling inference on Kubernetes | [`phase-2-capstone/`](phase-2-capstone/) |

Supporting docs:

- [`docs/glossary.md`](docs/glossary.md) — inference serving vocabulary, the literacy target for Phase 1
- [`docs/resources.md`](docs/resources.md) — curated books, papers, blogs, podcasts, and videos on LLM inference serving
- [`docs/archive/`](docs/archive/) — historical/superseded documentation only. Nothing in that folder reflects the current state of the project or should be used to guide new work; see its `README.md` for details.

## Docs site

This repo is published as a documentation site with [MkDocs](https://www.mkdocs.org/) + [Material](https://squidfunk.github.io/mkdocs-material/): **<https://kornsour.github.io/inference-platform/>** (built and deployed from `main` by [`.github/workflows/docs.yml`](.github/workflows/docs.yml)).

Run it locally:

```bash
python3 -m venv .venv-docs && source .venv-docs/bin/activate
pip install -r requirements-docs.txt
mkdocs serve   # live preview at http://127.0.0.1:8000
```

## How to use it

1. Start with [`docs/glossary.md`](docs/glossary.md) for the vocabulary.
2. Work the phases in order. Each phase folder has its own README with a concrete checklist and the artifacts to produce.
3. The Phase 2 capstone is the highest-leverage work — protect that time. If something has to give, cut reading breadth, not the build.

## Progress

- [x] **Phase 1** — Can explain prefill vs. decode and TTFT without notes; model served locally with measured TTFT / tokens-per-second; one-page brief written.
- [x] **Phase 2** — Model on Kubernetes via KServe + vLLM; KEDA autoscaling on an inference signal (custom Go external scaler); Prometheus/Grafana + SLO alert; load test on the local mock and on real GPUs; public [write-up](phase-2-capstone/WRITEUP.md). Remaining: live Envoy AI Gateway bring-up.
