# Using a local Windows GPU instead of renting

**Question:** can the platform use a Windows PC with a 12 GB GPU on the LAN
instead of a rented cloud GPU?

**Short answer:** Yes — and it's the right cost-conscious move for the *serving*
half of the capstone. A 12 GB consumer GPU runs real vLLM on a small/quantized
model and gives you genuine TTFT, throughput, and KV-cache numbers. It does
**not** let you demonstrate multi-replica *GPU* autoscaling — but you don't need
it to, because the autoscaling control loop is already proven with the mock.

## What the 12 GB GPU gives you (and what it doesn't)

| Goal | Single 12 GB GPU? |
| --- | --- |
| Real vLLM: PagedAttention, continuous batching, real KV-cache metrics | ✅ yes |
| Real TTFT / throughput / cost-per-token numbers for the write-up | ✅ yes |
| Validate the SAME ScaledObject/metrics against real vLLM (scale 0→1) | ✅ yes |
| Multi-replica **GPU** scale-out (N pods each on a GPU) | ❌ needs ≥2 GPUs |

The mock already covered the last row (KEDA 1→5 on the queue signal). So the
honest, strong story is a **hybrid**: *control loop validated on the mock at N
replicas; real engine characterized on one consumer GPU; identical metric names
mean the autoscaler is unchanged.* That also shows cost discipline — exactly the
judgment the platform role is testing for.

## What fits in 12 GB

vLLM needs room for **weights + KV cache + overhead**. Good fits:

- **3B–4B at FP16** (~6–8 GB) — comfortable, lots of KV-cache headroom.
- **7B–8B quantized** (AWQ / GPTQ INT4, ~5–6 GB weights) — fits with usable KV
  cache; closest to "production-ish" while staying in budget.
- Avoid 7B+ at FP16 (~14 GB+) — won't fit.

Start with something like `Qwen2.5-3B-Instruct` (FP16) or a 7B-AWQ build, and set
`--gpu-memory-utilization 0.90 --max-model-len 4096`.

## Two ways to wire it in

### Option A — vLLM in WSL2, cluster points at it (fastest to real numbers)

Run real vLLM on the Windows box and treat it as an external endpoint the local
`kind` cluster routes to. Least setup; gets you numbers today.

1. **Windows:** install WSL2 + the NVIDIA CUDA driver for WSL, then in Ubuntu:
   ```bash
   pip install vllm
   vllm serve Qwen/Qwen2.5-3B-Instruct --gpu-memory-utilization 0.90 \
     --max-model-len 4096 --host 0.0.0.0 --port 8000
   ```
2. Allow port 8000 through Windows Firewall; note the LAN IP (`ipconfig`).
3. **Cluster:** point a headless Service at it so manifests/dashboards are
   unchanged — see [`external-vllm.yaml`](external-vllm.yaml) (set the IP).
4. Benchmark it with the Phase 1 harness:
   `python ../../phase-1-foundations/benchmark.py --base-url http://<win-ip>:8000/v1 --model Qwen/Qwen2.5-3B-Instruct`

> Caveat: the GPU pod isn't *scheduled* by Kubernetes here — it's an external
> backend. Real engine numbers, but not the full "GPU on k8s" story.

### Option B — Windows box as a GPU agent node (authentic "GPU on k8s")

Join the Windows machine (via WSL2) to a real multi-node cluster so Kubernetes
schedules the vLLM pod onto the GPU and Prometheus scrapes it in-cluster.

1. **Windows/WSL2:** CUDA driver + [NVIDIA Container Toolkit].
2. Use **k3s** (kind can't span hosts): k3s server on one machine, join WSL2 as
   an agent — `curl -sfL https://get.k3s.io | K3S_URL=https://<server>:6443 K3S_TOKEN=<token> sh -`.
3. Install the **NVIDIA device plugin** so the node advertises `nvidia.com/gpu`.
4. Apply [`../k8s/inferenceservice.yaml`](../k8s/inferenceservice.yaml) (KServe +
   vLLM) with a smaller model; it lands on the GPU node. The existing
   ServiceMonitor + ScaledObject work unchanged.

> More setup (WSL2 GPU, device plugin, cross-host networking) but it's the real
> capstone artifact and still $0.

## Recommendation

Do **Option A first** — get real vLLM numbers into [`../WRITEUP.md`](../WRITEUP.md)
this week. Then, if you want the full story, graduate to **Option B**. Rent a
multi-GPU cloud node only if you specifically want to show *N-replica GPU* scale-
out — optional, since the mock already demonstrates the control loop.

[NVIDIA Container Toolkit]: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
