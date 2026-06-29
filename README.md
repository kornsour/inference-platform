# Inference Platform

A self-directed learning project to build genuine, hands-on depth in **LLM inference serving** — the platform layer underneath generative AI models: GPU scheduling, high-throughput serving engines, inference-aware autoscaling, and the observability and economics of running models at scale.

It is structured as a 6-month program aligned to two target roles on the same platform: **Staff Engineering Manager, Copilot API** (primary, more attainable) and **Principal Engineering Manager, AI Inference Platform** (stretch). The full strategy, gap analysis, and milestone tracking live in [`docs/project-plan.md`](docs/project-plan.md); the role crosswalk is in [`docs/role-comparison.md`](docs/role-comparison.md).

> **Scope note.** This repo is the **platform / SRE-leaning** inference project: how you *operate* model serving at scale (autoscaling, GitOps, observability, cost/SLOs). For the **low-level performance-engineering** counterpart — latency/throughput/memory benchmarking and kernel/KV-cache/batching/quantization optimizations with before/after numbers — see the companion repo **[`llm-inference-performance`](https://github.com/kornsour/llm-inference-performance)**.

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

The honest framing: ~70% of the target role is platform engineering and leadership I already do (Kubernetes, GitOps, observability, SLOs, multi-tenant platforms, capacity/cost discipline). The other ~30% — generative AI *serving* infrastructure — is a real, specific gap. This repo closes it by building, not just reading: standing up real inference endpoints, then a real autoscaling platform on Kubernetes, and writing up the results as portfolio evidence.

## Structure

| Phase | Months | Theme | Folder |
| --- | --- | --- | --- |
| **1** | 1–2 | Inference serving foundations — vocabulary, economics, first local serve | [`phase-1-foundations/`](phase-1-foundations/) |
| **2** | 3–4 | Hands-on platform build — the capstone: autoscaling inference on Kubernetes | [`phase-2-capstone/`](phase-2-capstone/) |
| **3** | 5–6 | Scale, leadership, and application — positioning and interview prep | [`phase-3-positioning/`](phase-3-positioning/) |

Supporting docs:

- [`docs/project-plan.md`](docs/project-plan.md) — the full plan (gap analysis, roadmap, risks)
- [`docs/role-comparison.md`](docs/role-comparison.md) — Staff EM vs. Principal EM crosswalk + coverage map
- [`docs/role.md`](docs/role.md) — the Staff EM job posting
- [`docs/glossary.md`](docs/glossary.md) — inference serving vocabulary, the literacy target for Phase 1
- [`docs/resources.md`](docs/resources.md) — curated books, papers, blogs, podcasts, and videos on LLM inference serving

## Docs site

This repo is published as a documentation site with [MkDocs](https://www.mkdocs.org/) + [Material](https://squidfunk.github.io/mkdocs-material/): **<https://kornsour.github.io/inference-platform/>** (built and deployed from `main` by [`.github/workflows/docs.yml`](.github/workflows/docs.yml)).

Run it locally:

```bash
python3 -m venv .venv-docs && source .venv-docs/bin/activate
pip install -r requirements-docs.txt
mkdocs serve   # live preview at http://127.0.0.1:8000
```

## How to use it

1. Read [`docs/project-plan.md`](docs/project-plan.md) end to end once.
2. Block recurring weekly time (6–10 focused hours).
3. Work the phases in order. Each phase folder has its own README with a concrete checklist and the artifacts to produce.
4. The Phase 2 capstone is the highest-leverage work — protect that time. If something has to give, cut reading breadth, not the build.

## Progress

- [x] **Phase 1** — Can explain prefill vs. decode and TTFT without notes; model served locally with measured TTFT / tokens-per-second; one-page brief written.
- [ ] **Phase 2** — Model on Kubernetes via KServe/Ray Serve + vLLM; KEDA autoscaling on an inference signal; Prometheus/Grafana dashboards; load test + public write-up.
- [ ] **Phase 3** — Scale & capacity study; reframed resume + positioning statement; leadership stories; ≥2 informational conversations; application submitted.
