# Phase 1 — Inference Serving Foundations

**Goal:** build the foundational literacy. By the end I can explain, without notes, how a request becomes tokens, where the time and cost go, and why inference autoscaling is fundamentally different from web-service autoscaling.

**Status: complete.** I served a model locally with measured TTFT and tokens/sec, and wrote the one-page brief ([`brief.md`](brief.md)).

## Checklist

### Learn (read and take notes against [`../docs/glossary.md`](../docs/glossary.md))

- [x] Inference request lifecycle: prefill (compute-bound) vs decode (memory-bound), and why that drives disaggregated serving.
- [x] KV cache and batching: PagedAttention, continuous batching, KV-cache utilization as the scaling signal.
- [x] Metrics that matter: TTFT, inter-token latency, throughput, and their trade-offs against cost.
- [x] Engine landscape: vLLM vs TensorRT-LLM vs SGLang, focused on trade-offs rather than memorizing benchmarks.
- [x] GPU economics: why accelerators dominate cost, and how quantization and batching change the math.

### Resources

- [x] vLLM docs and blog (PagedAttention, continuous batching), the canonical start.
- [x] NVIDIA Dynamo docs (disaggregated serving, autoscaling).
- [x] KServe docs, which anchor the Phase 2 build.
- [x] Chip Huyen, *Designing Machine Learning Systems* (serving and experiment-to-production chapters).
- [x] Latent Space podcast; Baseten / Fireworks / Together engineering blogs.

### Milestone

- [x] **Serve a model locally** behind an OpenAI-compatible endpoint ([`serve-local.md`](serve-local.md)).
- [x] **Measure TTFT and tokens/sec** under a few concurrency levels using [`benchmark.py`](benchmark.py).
- [x] **Write the one-page brief** "How inference serving works and why it is hard" ([`brief.md`](brief.md)).

## Success signal

I can explain prefill vs decode and TTFT without notes, I have a running endpoint, and the brief reads clearly to someone who isn't me.
