#!/usr/bin/env python3
"""Measure TTFT and throughput against an OpenAI-compatible inference endpoint.

Works with vLLM (:8000/v1), Ollama (:11434/v1), or any OpenAI-compatible server.
Streams completions so it can time the *first* token (TTFT) separately from the
rest of the decode, then sweeps a few concurrency levels to show the
latency/throughput trade-off that defines inference serving.

Usage:
    python benchmark.py --base-url http://localhost:8000/v1 \
        --model Qwen/Qwen2.5-1.5B-Instruct --concurrency 1 4 16

Dependencies: see requirements.txt (openai>=1.0).
"""
import argparse
import statistics
import threading
import time
from dataclasses import dataclass

from openai import OpenAI

PROMPT = (
    "You are a systems engineer. Explain, in about 200 words, why decode is "
    "memory-bandwidth-bound while prefill is compute-bound in LLM inference."
)


@dataclass
class RequestResult:
    ttft: float          # seconds to first token
    total: float         # seconds for the full completion
    output_tokens: int   # tokens generated (approximate, counts streamed chunks)


def run_one(client: OpenAI, model: str, max_tokens: int) -> RequestResult:
    start = time.perf_counter()
    ttft = None
    tokens = 0
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=max_tokens,
        temperature=0.7,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            if ttft is None:
                ttft = time.perf_counter() - start
            tokens += 1
    total = time.perf_counter() - start
    return RequestResult(ttft=ttft or total, total=total, output_tokens=tokens)


def run_concurrency_level(client, model, concurrency, requests, max_tokens):
    results: list[RequestResult] = []
    lock = threading.Lock()

    def worker(n):
        for _ in range(n):
            r = run_one(client, model, max_tokens)
            with lock:
                results.append(r)

    # divide requests across `concurrency` threads
    per = [requests // concurrency] * concurrency
    for i in range(requests % concurrency):
        per[i] += 1

    wall_start = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(n,)) for n in per if n]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - wall_start
    return results, wall


def pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round((p / 100) * (len(values) - 1)))))
    return values[k]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="not-needed", help="any value for local servers")
    ap.add_argument("--model", required=True)
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 16])
    ap.add_argument("--requests", type=int, default=None,
                    help="total requests per level (default: 4x concurrency)")
    ap.add_argument("--max-tokens", type=int, default=200)
    args = ap.parse_args()

    client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    print(f"\nEndpoint: {args.base_url}   Model: {args.model}\n")
    header = f"{'conc':>5} {'reqs':>5} {'TTFT p50':>9} {'TTFT p95':>9} {'tok/s/req':>10} {'total tok/s':>12}"
    print(header)
    print("-" * len(header))

    for c in args.concurrency:
        reqs = args.requests or (c * 4)
        results, wall = run_concurrency_level(client, args.model, c, reqs, args.max_tokens)
        ttfts = [r.ttft for r in results]
        per_req_tps = [r.output_tokens / r.total for r in results if r.total > 0]
        total_tokens = sum(r.output_tokens for r in results)
        system_tps = total_tokens / wall if wall > 0 else 0
        print(f"{c:>5} {reqs:>5} {pct(ttfts,50):>8.3f}s {pct(ttfts,95):>8.3f}s "
              f"{statistics.mean(per_req_tps):>9.1f} {system_tps:>11.1f}")

    print("\nRead it as: as concurrency rises, total tok/s should climb (better GPU\n"
          "utilization via batching) while TTFT p95 and per-request tok/s degrade.\n"
          "That trade-off is the whole game.\n")


if __name__ == "__main__":
    main()
