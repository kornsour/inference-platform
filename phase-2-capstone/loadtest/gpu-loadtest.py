#!/usr/bin/env python3
"""Dependency-free load generator for the real-GPU vLLM run (Phase 2).

Drives N concurrent streaming chat completions against an OpenAI-compatible
endpoint for a fixed duration, and reports client-side TTFT (time to first
token) percentiles, end-to-end latency, and output-token throughput. Pair the
output with vLLM's own /metrics (vllm:gpu_cache_usage_perc, num_requests_*,
generation_tokens_total) for the server-side truth.

Stdlib only — runs anywhere python3 is present (e.g. inside the GPU node's WSL).

Usage:
    python3 gpu-loadtest.py --host 127.0.0.1 --port 8000 --model qwen \
        --concurrency 16 --duration 60 --max-tokens 200
"""
import argparse, http.client, json, statistics, threading, time

PROMPT = "Summarize the trade-offs between throughput and latency in LLM serving."


def pct(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[k]


def worker(args, deadline, out, lock):
    local = []
    while time.time() < deadline:
        body = json.dumps({
            "model": args.model,
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": args.max_tokens,
            "stream": True,
        })
        t0 = time.time()
        ttft = None
        ntok = 0
        ok = False
        try:
            conn = http.client.HTTPConnection(args.host, args.port, timeout=180)
            conn.request("POST", "/v1/chat/completions", body,
                         {"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status == 200:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    if line.startswith(b"data:"):
                        data = line[5:].strip()
                        if data == b"[DONE]":
                            break
                        if ttft is None:
                            ttft = time.time() - t0
                        try:
                            j = json.loads(data)
                            if j["choices"][0]["delta"].get("content"):
                                ntok += 1
                        except Exception:
                            pass
                ok = True
            conn.close()
        except Exception:
            pass
        local.append((ok, ttft, ntok, time.time() - t0))
    with lock:
        out.extend(local)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--model", default="qwen")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--max-tokens", type=int, default=200)
    args = ap.parse_args()

    out, lock = [], threading.Lock()
    deadline = time.time() + args.duration
    wall0 = time.time()
    threads = [threading.Thread(target=worker, args=(args, deadline, out, lock))
               for _ in range(args.concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.time() - wall0

    ok = [r for r in out if r[0]]
    ttfts = [r[1] * 1000 for r in ok if r[1] is not None]   # ms
    toks = sum(r[2] for r in ok)
    lats = [r[3] for r in ok]

    print("==== gpu-loadtest results ====")
    print(f"model={args.model} concurrency={args.concurrency} duration={args.duration}s "
          f"max_tokens={args.max_tokens}")
    print(f"requests: {len(out)} total, {len(ok)} ok, {len(out) - len(ok)} failed")
    print(f"throughput: {len(ok)/wall:.2f} req/s, {toks/wall:.1f} output tok/s "
          f"(client-counted, {wall:.1f}s wall)")
    if ttfts:
        print(f"TTFT ms:  p50={pct(ttfts,50):.0f}  p95={pct(ttfts,95):.0f}  "
              f"p99={pct(ttfts,99):.0f}  mean={statistics.mean(ttfts):.0f}")
    if lats:
        print(f"e2e  s:   p50={pct(lats,50):.2f}  p95={pct(lats,95):.2f}  "
              f"mean={statistics.mean(lats):.2f}")


if __name__ == "__main__":
    main()
