# Phase 1 — Inference Serving Foundations (Months 1–2)

**Goal:** close the literacy gap. By the end, you can explain — without notes — how a request becomes tokens, where the time and cost go, and why inference autoscaling is fundamentally different from web-service autoscaling.

## Checklist

### Learn (read + take notes against [`../docs/glossary.md`](../docs/glossary.md))
- [ ] Inference request lifecycle: prefill (compute-bound) vs. decode (memory-bound), and why that drives disaggregated serving.
- [ ] KV cache & batching: PagedAttention, continuous batching, KV-cache utilization as the scaling signal.
- [ ] Metrics that matter: TTFT, inter-token latency, throughput, and their trade-offs against cost.
- [ ] Engine landscape: vLLM vs. TensorRT-LLM vs. SGLang — understand trade-offs, don't memorize benchmarks.
- [ ] GPU economics: why accelerators dominate cost; how quantization and batching change the math.

### Resources
- [ ] vLLM docs + blog (PagedAttention, continuous batching) — the canonical start.
- [ ] NVIDIA Dynamo docs (disaggregated serving, autoscaling).
- [ ] KServe docs — anchors the Phase 2 build.
- [ ] Chip Huyen, *Designing Machine Learning Systems* (serving + experiment-to-production chapters).
- [ ] Latent Space podcast; Baseten / Fireworks / Together engineering blogs.

### Milestone
- [ ] **Serve a model locally** behind an OpenAI-compatible endpoint — see [`serve-local.md`](serve-local.md).
- [ ] **Measure TTFT and tokens/sec** under a few concurrency levels — use [`benchmark.py`](benchmark.py).
- [ ] **Write the one-page brief** "How inference serving works and why it is hard" — fill in [`brief-template.md`](brief-template.md).

## Success signal

You can explain prefill vs. decode and TTFT without notes, you have a running endpoint, and the brief reads clearly to someone who isn't you.
