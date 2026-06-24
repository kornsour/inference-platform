# Real-GPU serving results (Phase 2)

Real vLLM serving numbers captured on the DIY cluster's GPU nodes, filling the
`_TODO: GPU_` section of the [WRITEUP](../WRITEUP.md). These come from an actual
vLLM engine (PagedAttention, continuous batching, true KV-cache metrics) — not the
local mock.

- **Serving manifest:** [`vllm-plain.yaml`](vllm-plain.yaml) — plain vLLM Deployment,
  `hostNetwork` + host DNS (the cross-node overlay is down under WSL2 mirrored mode, so
  pods can't reach CoreDNS — see [troubleshooting log](../../docs/cluster-troubleshooting-log.md)).
- **Load generator:** [`gpu-loadtest.py`](../loadtest/gpu-loadtest.py) — dependency-free,
  streaming, reports client TTFT + throughput; paired with server-side `vllm:*` metrics.
- **Method:** load driven on-node against `127.0.0.1:8000`; throughput cross-checked
  against `vllm:generation_tokens_total`; power via `nvidia-smi` under load.

---

## Run 1 — Qwen2.5-1.5B-Instruct (FP16) on RTX 4070 Laptop (8 GB)

`--gpu-memory-utilization 0.85`, `--max-model-len 8192`, single replica.

| Metric | Value |
|---|---|
| Model / quantization | Qwen2.5-1.5B-Instruct, **FP16** (unquantized) |
| KV-cache capacity | **6,382 GPU blocks × 16 = ~102,112 tokens** |
| TTFT p50 / p95 @ low load (1 stream) | **31 ms** / 809 ms¹ |
| TTFT p50 / p95 @ 24 concurrent | **60 ms** / **380 ms** |
| TTFT p50 / p95 @ 64 concurrent | ~100 ms / ~0.5–0.9 s |
| Peak sustained throughput | **~2,600 output tok/s** (64 concurrent) |
| Max concurrency observed | 64 in-flight, **queue still empty** |
| GPU at saturation | **98 % util, ~81 W** |
| Cost per 1M output tokens | **~$0.0015** (GPU energy only, $0.17/kWh)² |
| Errors | **0** across all runs |

¹ p95 at 1 stream is dominated by the cold first request (CUDA graph / cache warmup).
² Marginal GPU energy: 81 W ÷ 2,600 tok/s ≈ 0.0311 J/tok ≈ 0.0086 kWh per 1M tokens.
Excludes host idle draw and hardware amortization.

**Throughput / latency scaling (single replica):**

| Concurrency | Throughput (tok/s) | TTFT p50 | TTFT p95 | KV-cache used | Queue depth |
|---:|---:|---:|---:|---:|---:|
| 1  | 70    | 31 ms  | 809 ms¹ | minimal | 0 |
| 24 | 1,360 | 60 ms  | 380 ms  | low     | 0 |
| 64 | 2,600 | ~100 ms| ~0.5–0.9 s | **~11 %** | 0 |

!!! note "Key finding: a 1.5B model is compute-bound, not KV-bound, on an 8 GB card"
    Even at 64 concurrent requests the KV cache sat at **~11 %** and the queue never
    formed — throughput nearly doubled from 24→64 concurrency while TTFT crept up. The
    binding resource is **compute**, not KV-cache memory. So this model **cannot exercise
    the KV-cache-pressure / queue-depth signal** the autoscaler is built around — which is
    precisely the motivation for the larger-model run below. It also stayed under the
    **TTFT p95 < 1 s SLO** even fully saturated.

---

## Run 2 — Qwen2.5-3B-Instruct (FP16) on RTX 4070 Laptop (8 GB)

!!! warning "Finding: 3B FP16 barely fits an 8 GB card — it needs deliberate tuning"
    At the default `--gpu-memory-utilization 0.92` the engine **refused to start**:
    `Free memory on device cuda:0 (6.89/8.0 GiB) on startup is less than desired GPU memory
    utilization (0.92, 7.36 GiB)` — i.e. the ~6.2 GB of FP16 weights plus CUDA-graph memory
    left no room. It only booted after **`--enforce-eager`** (drops ~1 GB of CUDA-graph
    capture) **+ `--max-model-len 2048`** (shrinks the per-request KV reservation), at
    `--gpu-memory-utilization 0.85`. Lesson: an 8 GB consumer card is the hard ceiling for a
    3B model in FP16 — for real headroom you'd quantize (AWQ/GPTQ 4-bit).

| Metric | Value |
|---|---|
| Model / quantization | Qwen2.5-3B-Instruct, **FP16** (`--enforce-eager`, 2k ctx) |
| KV-cache capacity | **751 GPU blocks × 16 = ~12,016 tokens** (8.5× smaller than 1.5B) |
| TTFT p50 / p95 @ low load (1 stream) | **65 ms** / 353 ms |
| Single-stream throughput | ~36 output tok/s (~2× slower/token than 1.5B, as expected) |
| Peak throughput | ~670 output tok/s (saturated) |
| Max concurrency before queueing | **~6–8 full-context sequences** (KV-limited) |
| Cost per 1M output tokens | ~$0.005 (GPU energy, est.)¹ |
| Errors | 0 |

¹ Power not separately sampled; at ~80 W and ~670 tok/s the per-token energy is ~3–4× the
1.5B run — lower throughput dominates.

**Throughput / latency / KV-cache scaling (single replica):**

| Concurrency / output len | Throughput (tok/s) | TTFT p50 | TTFT p95 | KV-cache peak | Queue depth |
|---:|---:|---:|---:|---:|---:|
| 1 / 200    | 36  | 65 ms  | 353 ms   | minimal | 0 |
| 16 / 200   | 512 | 105 ms | 205 ms   | ~24 %   | 0 |
| 32 / 1500  | 670 | 484 ms | **4,115 ms** | **99.5 %** | **up to 12** |

!!! success "Key finding: the 3B run reproduces the autoscaler's trigger on real GPU"
    With an 8.5× smaller KV pool, driving 32 concurrent **long** (1,500-token) requests
    drove KV-cache utilization to **99.5 %**, formed a **queue of up to 12 waiting
    requests**, and pushed **TTFT p95 to 4.1 s** — well past the 1 s SLO. These are exactly
    the conditions the KEDA `ScaledObject` scales on (`gpu_cache_usage_perc > 0.7`,
    `num_requests_waiting > 3`). Where 1.5B stayed compute-bound and never tripped the
    signal, **3B exercises the inference-aware autoscaling path end to end on real hardware.**

### 1.5B vs 3B — the regime flip

| | Qwen2.5-1.5B | Qwen2.5-3B |
|---|---|---|
| Fits 8 GB? | Easily (FP16, 8k ctx) | Only with `enforce-eager` + 2k ctx |
| KV-cache capacity | ~102k tokens | ~12k tokens |
| Binding resource | **Compute** | **KV-cache memory** |
| Behavior under load | throughput scales, queue stays empty | KV saturates → **queue + SLO breach** |
| Triggers the autoscaler? | No | **Yes** |
| Peak throughput | ~2,600 tok/s | ~670 tok/s |

The pair tells the capacity-planning story: pick a model small enough to be compute-bound
and you get throughput but no natural scale signal; size up and the **KV cache becomes the
constraint** that the inference-aware autoscaler is built to react to.

## Run 3 — Two-GPU load-balanced scale-out

One Qwen2.5-1.5B replica **per physical GPU** (pod anti-affinity, `gpu-memory-utilization
0.80` to fit the smaller desktop card), fronted by an **external nginx round-robin LB**
across the two node IPs — [`vllm-2gpu.yaml`](vllm-2gpu.yaml).

!!! note "Why an external LB instead of a ClusterIP Service"
    The textbook approach is a ClusterIP Service load-balancing across the two replica
    pods. But cross-node ClusterIP DNATs to a pod IP on the other node, which rides the
    pod overlay — **down under WSL2 mirrored mode** (see
    [troubleshooting log](../../docs/cluster-troubleshooting-log.md)). With `hostNetwork`
    pods binding node IPs on real userspace sockets, an nginx LB targeting those node IPs
    load-balances over plain LAN TCP. This is the same `hostNetwork` workaround applied to
    the traffic plane.

Driving 32 concurrent requests through the LB, **both GPUs served in parallel**:

| GPU | Concurrent (running) | Tokens produced | Throughput |
|---|---:|---:|---:|
| Desktop RTX 3060 Ti | ~13 | 57,771 | 1,204 tok/s |
| Laptop RTX 4070 | ~19 | 55,515 | 1,157 tok/s |
| **Aggregate** | 32 | 113,286 | **2,360 tok/s** |

Client-side through the LB: **2,357 tok/s, TTFT p50 47 ms / p95 64 ms**, 0 errors.

!!! success "The scale-out result"
    nginx round-robin split requests ~evenly, and **both physical GPUs processed traffic
    concurrently** — aggregate throughput roughly **doubled** versus a single replica at the
    same per-replica load (~1,200 tok/s/card). This is genuine multi-GPU scale-out: two
    8 GB consumer cards on two physical machines behaving as one serving pool. The piece a
    home setup can't show that production does — cross-node tensor/pipeline parallelism over
    RDMA for models too big for one GPU — is called out in
    [cross-node networking](../../docs/cluster-cross-node-networking.md).

## Run 4 — KServe InferenceService (same model, the platform way)

The same Qwen2.5-1.5B served as a KServe `InferenceService` via the built-in
**huggingface** ServingRuntime (vLLM backend) instead of a hand-written Deployment —
[`kserve-inferenceservice.yaml`](kserve-inferenceservice.yaml). Mode: **RawDeployment**
(no Knative/Istio — see [architecture decisions](../architecture-decisions.md)). Ran on
the desktop 3060 Ti (the laptop was cordoned during this pass).

### Setup & friction (the operational cost)

Install was cert-manager → KServe controller → `ClusterServingRuntime`s, then the
`InferenceService`. Three frictions surfaced, **all tied to this cluster's constraints** —
and none of them exist with the plain Deployment:

| Friction | Cause | Fix |
|---|---|---|
| cert-manager **webhook unreachable** | webhook pods landed on the laptop; the desktop API server can't reach them across the broken overlay | **cordon the laptop** so webhook-backed controllers co-locate with the API server |
| KServe webhook **"no endpoints"** | applied cluster resources before the controller pod was Ready | wait for the controller `Available` |
| Deployment **rejected** (`8Gi > 2Gi`) | the huggingface runtime defaults `memory` limit to 2Gi; my `requests` exceeded it | set both `limits` and `requests` explicitly |

### Numbers

`--gpu-memory-utilization 0.80`, CUDA graphs on, **5,701 GPU KV blocks (~91k tokens)**.

| Concurrency | Throughput | TTFT p50 | TTFT p95 | Errors |
|---:|---:|---:|---:|---:|
| 1  | 97 tok/s    | 29 ms  | 246 ms | 0 |
| 64 | 2,549 tok/s | 141 ms | 368 ms | 0 |

### KServe vs. plain Deployment — the verdict

| | Plain Deployment | KServe InferenceService |
|---|---|---|
| Peak throughput (1.5B) | ~2,600 tok/s | ~2,550 tok/s |
| TTFT under load | comparable | comparable |
| Serving-performance overhead | — | **none measurable** (same vLLM engine) |
| To deploy | `Deployment` + `Service` + `PodMonitor` | cert-manager + KServe controller + CRDs + `InferenceService` |
| Failure surface | one container, explicit flags | controllers, webhooks, runtime defaults |
| What you get extra | — | declarative CRD, model abstraction, canary, storage-init, multi-model consistency |

!!! success "Finding: KServe's cost is operational, not runtime"
    Same engine, same numbers — **KServe adds no serving-performance penalty.** What it
    adds is a control plane (cert-manager + controller + webhooks) and abstraction that
    pays off when you operate *many* models/teams, but is pure overhead for a single
    workload — and on a degraded-networking cluster that overhead shows up as real setup
    friction (the table above). The plain Deployment shipped the same numbers with a
    fraction of the moving parts. Pick KServe for the **platform** (fleet of models,
    lifecycle, canary), not for a single model's throughput.
