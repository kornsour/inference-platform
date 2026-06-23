# Phase 1 — Inference Serving Foundations (Months 1–2)

**Goal:** close the literacy gap. By the end, you can explain — without notes — how a request becomes tokens, where the time and cost go, and why inference autoscaling is fundamentally different from web-service autoscaling.

**Status: In progress.** Model served locally with measured TTFT and tokens/sec; the one-page brief is still to be written.

## Checklist

### Learn (read + take notes against [`../docs/glossary.md`](../docs/glossary.md))

- [x] Inference request lifecycle: prefill (compute-bound) vs. decode (memory-bound), and why that drives disaggregated serving.
- [x] KV cache & batching: PagedAttention, continuous batching, KV-cache utilization as the scaling signal.
- [x] Metrics that matter: TTFT, inter-token latency, throughput, and their trade-offs against cost.
- [x] Engine landscape: vLLM vs. TensorRT-LLM vs. SGLang — understand trade-offs, don't memorize benchmarks.
- [x] GPU economics: why accelerators dominate cost; how quantization and batching change the math.

### Resources

- [x] vLLM docs + blog (PagedAttention, continuous batching) — the canonical start.
- [x] NVIDIA Dynamo docs (disaggregated serving, autoscaling).
- [x] KServe docs — anchors the Phase 2 build.
- [x] Chip Huyen, *Designing Machine Learning Systems* (serving + experiment-to-production chapters).
- [x] Latent Space podcast; Baseten / Fireworks / Together engineering blogs.

### Milestone

- [x] **Serve a model locally** behind an OpenAI-compatible endpoint — see [`serve-local.md`](serve-local.md).
- [x] **Measure TTFT and tokens/sec** under a few concurrency levels — use [`benchmark.py`](benchmark.py).
- [ ] **Write the one-page brief** "How inference serving works and why it is hard" — fill in [`brief-template.md`](brief-template.md).

## Success signal

You can explain prefill vs. decode and TTFT without notes, you have a running endpoint, and the brief reads clearly to someone who isn't you.
