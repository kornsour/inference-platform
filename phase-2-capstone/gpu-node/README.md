# Why local GPUs (instead of renting)

**Question:** can the platform run on consumer GPUs on the LAN instead of a rented
cloud GPU?

**Answer:** yes, and this project does exactly that. Two Windows machines with
**8 GB** consumer GPUs (an RTX 3060 Ti and an RTX 4070 Laptop), joined as a k3s
cluster, serve real vLLM and demonstrate genuine multi-replica GPU scale-out for
**$0**.

## What the local GPUs give you

| Goal | Status |
| --- | --- |
| Real vLLM: PagedAttention, continuous batching, real KV-cache metrics | :material-check: [done](real-gpu-results.md) |
| Real TTFT / throughput / cost-per-token numbers for the write-up | :material-check: [done](real-gpu-results.md) |
| Validate the SAME metrics/ScaledObject against real vLLM | :material-check: metrics flowing; KEDA-on-GPU next |
| Multi-replica **GPU** scale-out (one replica per card, load-balanced) | :material-check: [done](real-gpu-results.md) |

The control loop was first proven $0 on a metrics-faithful mock
([local validation](../local/README.md)). The two-GPU cluster then characterized the
real engine and reproduced the autoscaling trigger on real hardware. The metric
names are identical throughout, so the autoscaler is unchanged from mock to GPU.

## What fits in 8 GB

vLLM needs room for weights, KV cache, and overhead. From the actual runs
([results](real-gpu-results.md)):

- **1.5B FP16** (~3 GB): comfortable, with ~100k tokens of KV cache. It is compute-bound on
  an 8 GB card and never trips the KV-cache scaling signal.
- **3B FP16** (~6 GB): only fits with `--enforce-eager --max-model-len 2048`. It is
  KV-bound (~12k tokens of KV cache), which is what actually exercises the
  autoscaler's queue-depth and KV-cache signal.
- **7–8B quantized** (AWQ / GPTQ INT4, ~5 GB): the way to run a bigger model with
  usable KV-cache headroom.
- Avoid 7B+ at FP16 (~14 GB+). It won't fit.

## How it's wired: the DIY two-GPU cluster

Both Windows boxes run k3s inside WSL2; one is the server, both are GPU workers.
Kubernetes schedules a vLLM replica onto each card, Prometheus scrapes both, and an
external LB spreads traffic across them. Full setup is in the [runbook](diy-cluster.md),
and per-machine state is in the node docs
([PC](../../docs/cluster-node-windows-pc.md) ·
[laptop](../../docs/cluster-node-kaiser-laptop.md)). Size models to 8 GB, the
smaller card.

> The one genuinely hard part, cross-node pod networking under WSL2 mirrored mode,
> is written up as a [troubleshooting case study](../../docs/cluster-troubleshooting-log.md).
> The serving and metrics planes use a `hostNetwork` workaround.

### Faster alternative: external vLLM endpoint

To get engine numbers without the full cluster, run vLLM in WSL2 and point a headless
Service at it ([`external-vllm.yaml`](external-vllm.yaml)). That gives real numbers, but the pod
isn't Kubernetes-scheduled. The in-cluster two-GPU build above is the real artifact.

## Bottom line

Two 8 GB consumer GPUs on the LAN delivered the full serving result: real vLLM
numbers and multi-replica scale-out, at **$0**. Renting a multi-GPU cloud node is
only worth it for what two 8 GB cards genuinely can't do, namely a single model too large for
one card, or cross-node tensor/pipeline parallelism over RDMA.
