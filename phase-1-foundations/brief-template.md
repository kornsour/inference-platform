# How inference serving works and why it is hard

> One page, for yourself. If you can write it clearly, you've closed the literacy gap.
> It also becomes raw material for interview answers. Keep it to ~1 page.

## 1. How a request becomes tokens
*(prompt in → prefill → decode loop → tokens out. Name the two phases and their bottlenecks.)*

## 2. Where the time goes
*(TTFT = queue + prefill; inter-token latency = decode. What dominates and when?)*

## 3. Where the cost goes
*(GPU is the dominant cost. What drives utilization? How do batching and quantization change cost-per-million-tokens?)*

## 4. Why inference autoscaling ≠ web-service autoscaling
*(CPU is the wrong signal. KV-cache utilization, queue depth, TTFT p95 are the real saturation signals. Why?)*

## 5. What I measured
*(Paste your `benchmark.py` results. What happened to TTFT and total tok/s as concurrency rose? Did it match the theory?)*

| concurrency | TTFT p50 | TTFT p95 | tok/s/req | total tok/s |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## 6. The one thing that surprised me
*(...)*
