# Inference Serving Glossary

The literacy target for Phase 1. Goal: be able to explain each of these out loud, without notes, and say *why it matters for a platform*.

## Request lifecycle

- **Prefill** — the first forward pass that processes the entire input prompt and produces the first output token. **Compute-bound**: work scales with prompt length, saturating GPU compute (FLOPs). Long prompts make prefill expensive.
- **Decode** — the autoregressive loop that generates one token at a time after prefill. **Memory-bandwidth-bound**: each step reads the whole model + KV cache from GPU memory to produce one token, so it's limited by memory bandwidth, not compute.
- **Disaggregated prefill/decode** — running prefill and decode on *separate* GPU pools because they have opposite bottlenecks. Lets each pool be sized and scaled independently. The headline architecture in NVIDIA Dynamo and llm-d.

## Memory & batching

- **KV cache** — cached key/value tensors for every token already processed, so decode doesn't recompute attention over the whole sequence each step. Grows linearly with sequence length × batch size. It is the dominant consumer of GPU memory during serving, and therefore the real ceiling on concurrency.
- **PagedAttention** — vLLM's technique that manages KV cache in fixed-size "pages" (like OS virtual memory) instead of one contiguous block per request. Slashes memory fragmentation, so you fit far more concurrent requests on the same GPU.
- **Continuous (in-flight) batching** — instead of waiting to assemble a fixed batch, the scheduler adds and evicts requests from the running batch every decode step. New requests join immediately; finished ones free their slots immediately. This is the single biggest throughput win in modern serving.

## Metrics / SLIs

- **TTFT (Time To First Token)** — latency from request arrival to the first token. Dominated by queueing + prefill. The metric users *feel* first; the primary latency SLI.
- **ITL / TPOT (Inter-Token Latency / Time Per Output Token)** — time between successive output tokens during decode. Drives perceived "typing speed."
- **Throughput** — tokens per second (and requests per second) the system sustains across all concurrent requests. Trades off against latency: bigger batches raise throughput but worsen TTFT/ITL.
- **Goodput** — throughput that *also* meets latency SLOs. The number that actually matters for capacity planning.

## Engines (the layer that runs the model)

- **vLLM** — open-source, PagedAttention + continuous batching, OpenAI-compatible server. The fast path to a running endpoint and the default starting point.
- **TensorRT-LLM** — NVIDIA's compiled-kernel engine for peak throughput/latency on NVIDIA hardware. More setup, highest performance.
- **SGLang** — engine with RadixAttention (prefix-cache reuse), strong for structured generation and high-concurrency workloads.

## Servers / platforms (the layer that operates engines)

- **KServe** — CNCF project; standardizes model serving on Kubernetes. Its `LLMInferenceService` abstracts GPU scheduling, autoscaling, and prefill/decode disaggregation. The Phase 2 anchor.
- **Ray Serve** — Python-native serving with GPU scheduling, KV-cache-aware autoscaling, and canary patterns.
- **NVIDIA Dynamo** (Dynamo-Triton) — successor to Triton; disaggregated serving and smart routing across GPU pools.
- **Envoy AI Gateway** — token-aware rate limiting, model routing, multi-tenant traffic shaping in front of the engines.

## Scaling & economics

- **Inference-aware autoscaling** — scaling on signals like TTFT p95, queue depth, or KV-cache utilization rather than CPU. CPU is nearly meaningless for GPU inference; KV-cache pressure and latency are the real saturation signals. **KEDA** drives this from Prometheus metrics.
- **GPU economics** — accelerators are the dominant cost. Utilization (keeping the GPU busy with useful batched work), **quantization** (lower-precision weights → more fits per GPU, faster decode), and batching all change cost-per-million-tokens. This is where platform cost discipline transfers directly.
- **Cost-per-million-tokens** — the unit economic that ties latency, batching, utilization, and GPU price together. The number to optimize and to report in the capstone write-up.
