# AI Inference

A hands-on project on **LLM inference serving** — the platform layer underneath generative AI models: GPU scheduling, high-throughput serving engines, inference-aware autoscaling, and the observability and economics of running models at scale. It pairs a literacy track (vocabulary, measured local serving) with a build track (an autoscaling inference platform on Kubernetes).

## What is AI inference?

**Inference** is the *serving* phase of a model's lifecycle — taking an already-trained model and running it to produce outputs in response to live requests. It's the counterpart to training: training builds the model's weights; inference *uses* those weights to generate tokens for users. Every time you send a prompt to a chatbot, a coding assistant, or any generative AI product, you are triggering an inference request.

For a large language model, a single request runs in two distinct phases:

- **Prefill** — the first forward pass that processes the entire input prompt and produces the first output token. It is **compute-bound**: work scales with prompt length and saturates GPU compute (FLOPs).
- **Decode** — the token-by-token generation that follows. It is **memory-bandwidth-bound**: each new token depends on the growing KV cache rather than raw compute.

### Why it matters

- **It's where the cost lives.** A model is trained once but served billions of times. Accelerators (GPUs) are the dominant cost, so the unit economic that matters is **cost-per-million-tokens** — driven by utilization, batching, and quantization.
- **It's where the user experience lives.** Latency signals like **time-to-first-token (TTFT)** and tokens-per-second directly shape how a product feels. The serving layer, not the model weights, determines whether responses feel instant or sluggish.
- **It scales differently from normal infrastructure.** CPU utilization is nearly meaningless for GPU inference; the real saturation signals are KV-cache pressure, queue depth, and tail latency. This requires **inference-aware autoscaling** rather than the CPU-based autoscaling most platforms use.

## What's here

| Section | What it covers |
| --- | --- |
| [Glossary](docs/glossary.md) | The inference-serving vocabulary — request lifecycle, batching, metrics, engines, autoscaling. |
| [Phase 1 — Foundations](phase-1-foundations/README.md) | Serving a model locally and measuring TTFT / throughput, with a written brief on how serving works and why it's hard. |
| [Phase 2 — Capstone](phase-2-capstone/README.md) | Building an autoscaling LLM inference platform on Kubernetes (KServe + vLLM + KEDA + Prometheus/Grafana). |
| [Resources](docs/resources.md) | Curated papers, books, blogs, podcasts, and videos on LLM inference serving. |

Start with the [Glossary](docs/glossary.md) for the vocabulary, then the [Phase 1 results](phase-1-foundations/results.md) for measured behavior on real hardware.
