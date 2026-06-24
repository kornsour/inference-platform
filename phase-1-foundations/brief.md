# How inference serving works and why it is hard

## 1. How a request becomes tokens

In LLM inference serving, a request is processed in two distinct phases: **Prefill** and **Decode**.

- **Prefill (Compute-Bound):** When a prompt enters the system, the model processes all input tokens in parallel. This phase computes the initial key-value (KV) activations for the entire prompt and generates the first output token. Because all input tokens are processed simultaneously, this phase saturates the GPU's execution units (FLOPs) and is highly **compute-bound**. The bottleneck here is how fast the GPU can execute matrix multiplications.
- **Decode (Memory-Bandwidth-Bound):** Once the first token is generated, the model enters a sequential, token-by-token loop. In each step, the model takes only the single previously generated token, along with the saved history of all prior tokens (the KV cache), to generate the next token. Because this step processes only one token at a time, it cannot saturate the GPU compute cores. Instead, it must load the massive model weights and the growing KV cache from High Bandwidth Memory (HBM) to the GPU's SRAM for every single token generated. Thus, the decode phase is heavily **memory-bandwidth-bound**.

## 2. Where the time goes

The latency a user experiences is split into two primary metrics:

- **Time-to-First-Token (TTFT):** TTFT is the sum of **Queue Time** (waiting for available compute/memory slot) and **Prefill Time** (time to process the prompt and emit the first token).
  - _What dominates and when?_ At low concurrency, TTFT is dominated by the prefill compute time. At high concurrency, TTFT is heavily dominated by **queue time** as new requests wait for existing generations to free up KV cache capacity or GPU execution cycles.
- **Inter-Token Latency (ITL):** ITL is the time elapsed between generating consecutive tokens during the decode phase.
  - _What dominates and when?_ ITL is dominated by memory bandwidth bottlenecks: loading the model parameters and the KV cache from HBM to SRAM. As the sequence length grows, the KV cache size grows, increasing memory transfer time. Under high concurrency, concurrent decode steps must share memory bandwidth, which can cause ITL to degrade if the system is saturated.

## 3. Where the cost goes

Accelerators (GPUs) dominate the operational cost of serving LLMs, meaning the primary economic goal is maximizing GPU utilization.

- **Driving Utilization:** To keep the GPU busy and amortize the cost of loading model weights, serving engines use **batching**. By grouping multiple requests together, the model weights are loaded once from HBM to SRAM and shared across all batched requests.
- **Continuous Batching:** Traditional static batching requires all requests in a batch to start and finish together, wasting GPU cycles when some requests finish early (padding). Modern engines use **continuous batching** (or iteration-level scheduling), where new requests are injected into the batch dynamically at the iteration boundary, and completed requests are evicted immediately.
- **Quantization:** Weight quantization (e.g., converting FP16 weights to INT8 or INT4) reduces the memory footprint of the model weights. This directly reduces the amount of data transferred from HBM to SRAM per token, reducing the memory bandwidth bottleneck and speeding up decode. It also frees VRAM, leaving more room for the KV cache so a single GPU can hold much larger batch sizes (higher throughput / lower cost-per-million-tokens). Quantizing the KV cache itself is a separate, explicitly-enabled technique.

## 4. Why inference autoscaling ≠ web-service autoscaling

Traditional web applications are typically scaled based on **CPU utilization** or **request rate**. These signals fail for LLM inference serving:

- **GPU "utilization %" is the wrong signal:** `nvidia-smi` utilization measures the *fraction of time a kernel was active*, not how saturated the hardware is. A single memory-bound decode can show ~100% utilization while real compute (FLOP) headroom is enormous, so the number does not track serving capacity.
- **Memory-used is also misleading:** engines like vLLM *pre-allocate* most of VRAM for the KV-cache pool at startup, so memory-used reads as pegged regardless of actual load. Neither classic web-scaling signal reflects how full the system really is.
- **KV-Cache Saturation:** The true resource bottleneck is the **KV Cache capacity** (VRAM). When the KV cache is full, the engine cannot accept new requests even if it has compute headroom, leading to requests queueing up or being preempted (swapped/recomputed).
- **Queue Depth and TTFT p95:** Because LLM generation is stateful and long-running, request queues build up rapidly. A sudden spike in requests increases queue time exponentially, causing TTFT p95 to spike while the actual GPU execution time per token remains relatively flat. Therefore, autoscaling must react to queue depth, KV cache utilization, or SLO-based targets like TTFT p95.

## 5. What I measured

The benchmark results from running a local OpenAI-compatible endpoint (Ollama using `llama.cpp` on an Apple M5 Pro, 24 GB unified memory, Q4_K_M quantization) show how concurrency affects performance. The table below displays results for `qwen2.5:14b-instruct`, measured at `--max-tokens 128` with 4 requests per concurrency level (recorded in [results.md](results.md)):

| concurrency | TTFT p50 | TTFT p95 | tok/s/req | total tok/s |
| :---------: | :------: | :------: | :-------: | :---------: |
|      1      |  0.11s   |  3.22s   |   26.6    |    25.2     |
|      2      |  4.26s   |  4.33s   |   18.8    |    30.2     |
|      4      |  8.57s   |  12.78s  |   15.6    |    30.2     |

- **TTFT Degradation:** As concurrency increases from 1 to 4, TTFT p50 degrades dramatically (0.11s → 8.57s). This demonstrates prefill queueing in action.
- **Throughput Plateau:** Total throughput plateaus very early around ~30 tok/s. This matches the theory of my setup: Ollama (llama.cpp) lacks kernel-level continuous batching and PagedAttention, meaning it does not scale throughput efficiently with concurrency. To see throughput scale with batch size, a real serving engine like vLLM is required.

## 6. The one thing that surprised me

**Reasoning/thinking models consume massive capacity and introduce measurement challenges if not handled correctly.**
During the benchmark of reasoning models (`qwen3.5` and `gemma4`), they streamed their chain-of-thought on a separate `reasoning_content` API channel. The initial version of [benchmark.py](benchmark.py) only counted standard `content`, reporting **0 tokens/sec** because the model spent its entire token budget "thinking." Furthermore, in quality testing, reasoning models sometimes over-thought (consuming their full ~1,500-token budget on internal reasoning) and ran out of their token budget before emitting any final answer.

This taught two critical lessons:

1. **Reasoning tokens are real capacity costs:** Every reasoning token consumes GPU compute and grows the KV cache exactly like user-facing content.
2. **Usability and Cost Trade-offs:** A model that over-thinks is not only a poor user experience (truncated responses) but also a massive drain on serving platform resources.
