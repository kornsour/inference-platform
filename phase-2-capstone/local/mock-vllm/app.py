"""Metrics-faithful mock of a vLLM OpenAI-compatible server.

The Phase 2 capstone is about the *autoscaling control loop*, not model quality.
This service lets you build and validate that loop locally with no GPU: it
speaks the OpenAI streaming chat API and exposes Prometheus metrics using the
**same metric names a real vLLM emits** —

    vllm:num_requests_running        gauge
    vllm:num_requests_waiting        gauge   <- KEDA queue-depth trigger
    vllm:gpu_cache_usage_perc        gauge   <- KEDA KV-cache trigger
    vllm:time_to_first_token_seconds histogram
    vllm:time_per_output_token_seconds histogram
    vllm:generation_tokens_total     counter
    vllm:request_success_total       counter{finished_reason}  <- availability/error-rate SLIs

Because the names match, the Prometheus queries, PodMonitor, KEDA ScaledObject,
and Grafana panels you build against this mock work unchanged when a real vLLM
on a GPU replaces it. Concurrency is bounded by CAPACITY "decode slots" (a stand
-in for KV-cache capacity); requests beyond that queue and count as *waiting*,
which is exactly the signal that should drive scale-out.

Tunables (env): CAPACITY, GEN_TOKENS, TPOT_SECONDS, PREFILL_SECONDS, ERROR_RATE
(fraction of requests to fail with a simulated engine abort — 0 by default;
dial it up to drive the error-rate/availability SLIs and their alerts for a
game day without touching real traffic).
"""
import asyncio
import json
import os
import random
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

CAPACITY = int(os.environ.get("CAPACITY", "4"))             # concurrent decode slots
GEN_TOKENS = int(os.environ.get("GEN_TOKENS", "200"))       # tokens per response
TPOT = float(os.environ.get("TPOT_SECONDS", "0.05"))        # time per output token
PREFILL = float(os.environ.get("PREFILL_SECONDS", "0.30"))  # prompt processing time
ERROR_RATE = float(os.environ.get("ERROR_RATE", "0"))       # fraction of requests to abort

# vLLM-compatible metrics (colon names match the real engine's output).
m_running = Gauge("vllm:num_requests_running", "Requests in the running batch")
m_waiting = Gauge("vllm:num_requests_waiting", "Requests queued for a decode slot")
m_kv = Gauge("vllm:gpu_cache_usage_perc", "KV-cache utilization (0-1)")
m_ttft = Histogram("vllm:time_to_first_token_seconds", "Time to first token",
                   buckets=(.05, .1, .25, .5, 1, 2, 5, 10))
m_tpot = Histogram("vllm:time_per_output_token_seconds", "Time per output token",
                   buckets=(.01, .025, .05, .1, .25, .5))
m_gen = Counter("vllm:generation_tokens_total", "Total generated tokens")
m_requests = Counter("vllm:request_success_total", "Finished requests by outcome",
                     ["finished_reason"])

app = FastAPI(title="mock-vllm")

_slots = asyncio.Semaphore(CAPACITY)
_state = {"running": 0, "waiting": 0}
_lock = asyncio.Lock()


async def _sync_gauges():
    m_running.set(_state["running"])
    m_waiting.set(_state["waiting"])
    # KV-cache pressure scales with how many slots are busy — the same thing
    # that caps concurrency on a real GPU during decode.
    m_kv.set(min(1.0, _state["running"] / CAPACITY))


class Slot:
    """Acquire a decode slot, accounting for queue (waiting) vs running."""

    async def __aenter__(self):
        async with _lock:
            _state["waiting"] += 1
            await _sync_gauges()
        await _slots.acquire()
        async with _lock:
            _state["waiting"] -= 1
            _state["running"] += 1
            await _sync_gauges()
        return self

    async def __aexit__(self, *exc):
        _slots.release()
        async with _lock:
            _state["running"] -= 1
            await _sync_gauges()


def _chunk(content):
    return {"object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"content": content},
                         "finish_reason": None}]}


@app.post("/v1/chat/completions")
async def chat(body: dict):
    n = int(body.get("max_tokens") or GEN_TOKENS)
    stream = bool(body.get("stream"))
    model = body.get("model", "mock-vllm")

    # Optional error injection (ERROR_RATE) — a pre-flight admission failure,
    # same shape a real engine abort or an overloaded queue rejection takes:
    # counted, never queued, never occupies a decode slot.
    if ERROR_RATE and random.random() < ERROR_RATE:
        m_requests.labels(finished_reason="abort").inc()
        return JSONResponse(
            {"error": {"message": "simulated engine abort", "type": "server_error"}},
            status_code=500,
        )

    async def run(emit):
        start = time.perf_counter()
        async with Slot():
            await asyncio.sleep(PREFILL)            # prefill
            m_ttft.observe(time.perf_counter() - start)
            for _ in range(n):
                t = time.perf_counter()
                await asyncio.sleep(TPOT)           # one decode step
                m_tpot.observe(time.perf_counter() - t)
                m_gen.inc()
                await emit("token ")

    if stream:
        async def sse():
            queue: asyncio.Queue = asyncio.Queue()

            async def producer():
                await run(lambda tok: queue.put(tok))
                m_requests.labels(finished_reason="stop").inc()
                await queue.put(None)

            task = asyncio.create_task(producer())
            while True:
                tok = await queue.get()
                if tok is None:
                    break
                yield f"data: {json.dumps(_chunk(tok))}\n\n"
            await task
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    # non-streaming: accumulate
    parts = []
    await run(lambda tok: parts.append(tok) or asyncio.sleep(0))
    m_requests.labels(finished_reason="stop").inc()
    text = "".join(p if isinstance(p, str) else "" for p in parts)
    return JSONResponse({
        "object": "chat.completion", "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "usage": {"completion_tokens": n},
    })


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"status": "ok", "capacity": CAPACITY}


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": "mock-vllm", "object": "model"}]}
