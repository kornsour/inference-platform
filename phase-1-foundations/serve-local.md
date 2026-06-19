# Serving a model locally

Two paths. Start with whichever matches your hardware, then graduate to vLLM — vLLM is the engine you'll carry into the Phase 2 capstone, so the time spent there compounds.

## Option A — Ollama (gentlest first step, CPU or Apple Silicon)

Good for a first endpoint with zero GPU. Runs on a Mac.

```bash
# install: https://ollama.com/download  (or: brew install ollama)
ollama serve &                 # starts an OpenAI-compatible server on :11434
ollama pull llama3.2:1b        # small, fast to download
ollama run llama3.2:1b "Explain KV cache in one sentence."
```

OpenAI-compatible endpoint: `http://localhost:11434/v1` (any value works as the API key).

> Note: Ollama doesn't expose continuous batching / PagedAttention the way vLLM does, so its numbers won't teach you the *serving* lessons. It's here to get you a working endpoint fast.

## Option B — vLLM (the real thing, needs an NVIDIA GPU)

This is what matters. Rent a single GPU (RunPod / Lambda / Modal — budget a few dollars/hour, **shut it down between sessions**).

```bash
pip install vllm
# serve an open-weights model behind an OpenAI-compatible endpoint on :8000
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.90
```

OpenAI-compatible endpoint: `http://localhost:8000/v1`. Watch the startup logs — vLLM prints the KV-cache size and how many concurrent sequences it can hold. That number *is* your concurrency ceiling; connect it back to the glossary.

### Things to observe while it runs
- The reported **KV cache blocks** and max concurrency.
- How TTFT changes as you raise concurrency (prefill queueing).
- How throughput (tokens/sec) climbs with batch size while per-request latency degrades — the core trade-off.

## Then benchmark it

Point [`benchmark.py`](benchmark.py) at whichever endpoint you started:

```bash
pip install -r requirements.txt
python benchmark.py --base-url http://localhost:8000/v1 --model Qwen/Qwen2.5-1.5B-Instruct --concurrency 1 4 16
# or against Ollama:
python benchmark.py --base-url http://localhost:11434/v1 --model llama3.2:1b --concurrency 1 4 16
```

Record the results in your one-page brief.
