# Phase 1 — Local Serving Results

Measured TTFT and throughput for several open-weights models served locally behind an OpenAI-compatible endpoint, using [`benchmark.py`](benchmark.py). This is the Phase 1 milestone artifact: a running endpoint plus numbers that make the latency/throughput trade-off concrete.

## Environment

| | |
| --- | --- |
| Machine | Apple M5 Pro, 24 GB unified memory |
| Server | Ollama (OpenAI-compatible endpoint on `:11434/v1`) |
| Quantization | Q4_K_M for all models |
| Harness | `benchmark.py`, streaming, 4 requests/level, `--max-tokens 128` |

> **Caveat: this is not a real serving engine.** Ollama (llama.cpp) doesn't do PagedAttention or continuous batching, so total throughput barely rises with concurrency here. That flat line is itself the lesson: to see throughput scale with batch size you need vLLM on a GPU, which is the Phase 2 capstone. These numbers measure this laptop, not a production serving stack.

## Results

Sweeping concurrency 1 → 2 → 4. `tok/s/req` is mean per-request generation speed; `total tok/s` is system throughput across all concurrent requests.

| Model | Params | Type | conc | TTFT p50 | TTFT p95 | tok/s/req | total tok/s |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `qwen3.5:4b` | 4.7B | thinking | 1 | 0.17s | 2.67s | 48.9 | 43.0 |
| | | | 2 | 1.78s | 1.94s | 37.2 | 60.9 |
| | | | 4 | 3.71s | 5.45s | 30.0 | 60.2 |
| `gemma4:e4b` | 8B | thinking | 1 | 0.29s | 3.39s | 48.4 | 41.3 |
| | | | 2 | 1.94s | 2.14s | 37.3 | 61.0 |
| | | | 4 | 4.02s | 5.86s | 29.6 | 59.9 |
| `qwen2.5:14b-instruct` | 14.8B | standard | 1 | 0.11s | 3.22s | 26.6 | 25.2 |
| | | | 2 | 4.26s | 4.33s | 18.8 | 30.2 |
| | | | 4 | 8.57s | 12.78s | 15.6 | 30.2 |
| `qwen3.5:27b` ¹ | 27.8B | thinking | 1 | 0.40s | 9.42s | 9.3 | 8.2 |
| | | | 2 | 0.46s | 8.90s | 9.5 | 12.7 |

¹ `qwen3.5:27b` is 17 GB of weights on a 24 GB machine, so it runs at the memory ceiling (free RAM dropped to ~6% during the run). It completes correctly but ~5× slower than the 4B, and is benchmarked only at low concurrency because higher concurrency thrashes swap. Measured at `--max-tokens 128`, 2 requests/level.

## How to read it

- **TTFT degrades with concurrency.** As requests pile up, each one queues behind others in prefill. TTFT p50 for `qwen2.5:14b` goes 0.11s → 4.26s → 8.57s. This is the latency users feel first.
- **Per-request throughput drops, system throughput rises a little.** `qwen3.5:4b` per-request tok/s falls 48.9 → 30.0 while total climbs 43 → 60. You trade individual latency for aggregate work, and that trade-off is the whole game of inference serving.
- **Total throughput plateaus fast.** It flattens around ~60 tok/s by concurrency 2 because Ollama isn't batching at the kernel level. A real engine (vLLM) would keep climbing far higher before saturating, and the gap between these two curves is exactly why the serving engine matters.
- **Model size dominates speed.** 4.7B runs at ~49 tok/s and 27.8B at ~9 tok/s on the same box, and the 27B only fits because of Q4 quantization, at the cost of sitting on the memory edge. This is the quantization-vs-capacity trade in miniature.

## Engineering note: counting "thinking" tokens

Most current open models (`qwen3.5`, `gemma4`) are reasoning models: they stream their chain-of-thought on a separate `reasoning_content` channel, distinct from the user-facing `content`. The first version of `benchmark.py` counted only `content`, so a model that spent its whole token budget thinking reported **0 tokens/sec**, which was a measurement bug, not a slow model.

The fix was to count every generated token, reasoning or content. From a serving standpoint that's the correct definition anyway, since every decoded token consumes GPU compute and grows the KV cache, whether or not the user ever sees it. Reasoning models, by generating far more tokens per request, put more pressure on the exact bottlenecks (KV cache, decode bandwidth) that Phase 2 is about.

## Quality comparison

Speed is only half the picture, since a fast model that answers badly is worthless. `benchmark.py --quality` runs a small categorized prompt suite (factual recall, reasoning/math, instruction-following, coding, conciseness, summarization) across several models, captures each answer for human review, and optionally scores them with a **blinded LLM judge** against per-prompt rubrics.

Example run, `qwen3.5:4b` vs `gemma4:e4b`, judged by `qwen2.5:14b-instruct`:

| Model | Mean judge score (1–5) | Notes |
| --- | ---: | --- |
| `gemma4:e4b` | **4.17** | Consistent across categories |
| `qwen3.5:4b` | 2.83 | Strong on factual/instruction/coding (4–5); fails conciseness |

The interesting finding is why qwen3.5:4b loses points: on the simplest prompts ("What does TTFT stand for?") it **over-thinks**. It spends its entire token budget in the reasoning channel and never emits a final answer. That's a real usability cost of reasoning models, and a measurement trap, so the harness flags these as `truncated/no-answer` rather than silently scoring an empty answer as wrong.

Two lessons that carry into platform work:

- **Reasoning tokens are real load.** A model that thinks for 1,500 tokens to answer "what does TTFT mean" consumes 1,500 tokens of decode compute and KV cache. Quality and serving cost are coupled, so over-thinking is both a UX and a capacity problem.
- **LLM-as-judge is a noisy proxy, not ground truth.** The judge has its own biases; the harness blinds it (answers relabeled and shuffled) and always writes the full answers to a report so a human can verify the ranking.

## Reproduce

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# performance: latency + throughput sweep
python benchmark.py --base-url http://localhost:11434/v1 \
  --model qwen3.5:4b --concurrency 1 2 4 --max-tokens 128

# quality: side-by-side answers + optional blinded LLM judge
python benchmark.py --base-url http://localhost:11434/v1 --quality \
  --models qwen3.5:4b gemma4:e4b --judge qwen2.5:14b-instruct
```

See [`serve-local.md`](serve-local.md) for standing up the endpoint.
