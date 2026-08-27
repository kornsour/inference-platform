# Architecture decisions and trade-offs

The capstone serves the same model (Qwen2.5-1.5B on vLLM) three different ways across its layers. This page records why I made each choice, what it buys, and what it costs. Numbers for each path live in [real-gpu-results.md](gpu-node/real-gpu-results.md).

There are three independent decisions, from application down to substrate:

1. **Serving layer:** plain Deployment vs KServe.
2. **Traffic plane:** ClusterIP Service vs external load balancer.
3. **Networking substrate:** the WSL2 constraint that shapes the two above.

---

## 1. Serving layer: plain vLLM Deployment vs KServe InferenceService

Both run the identical vLLM engine. The difference is everything around the engine.

### Plain vLLM `Deployment` (the first build)

A bare `Deployment` plus `Service` plus `PodMonitor` running `vllm/vllm-openai`
([vllm-plain.yaml](gpu-node/vllm-plain.yaml)).

| | |
|---|---|
| :material-thumb-up: **Benefits** | Minimal moving parts; nothing to install beyond the workload. Fastest path to real numbers. Trivial to debug, with one container and explicit vLLM flags. Works on a constrained or degraded cluster with no extra dependencies. Full, transparent control of every engine arg. |
| :material-thumb-down: **Downsides** | You hand-wire everything the platform doesn't give you: scaling, metrics scraping, load balancing, canary, model lifecycle. No standard CRD, so multi-model and GitOps consistency is on you. No model abstraction, so you own the container and args. Reinvents what a model-serving platform exists to provide. |

**Use when:** you need real engine numbers fast, the cluster is small or constrained, or
you want maximum control and minimum surface area.

### KServe `InferenceService`, RawDeployment mode (the second build)

The same model declared as an `InferenceService` using the built-in **huggingface**
ServingRuntime (vLLM backend), in [kserve-inferenceservice.yaml](gpu-node/kserve-inferenceservice.yaml).

| | |
|---|---|
| :material-thumb-up: **Benefits** | One declarative CRD instead of a hand-rolled Deployment, Service, and scaler, which is GitOps-friendly and consistent across many models. **Model abstraction**: `modelFormat: huggingface` pulls and serves a model without writing a container spec. Standard predictor/transformer/explainer structure, storage-initializer model caching, canary and traffic-splitting, and consistent metrics and payload logging built in. A real model-serving platform, not a one-off workload. |
| :material-thumb-down: **Downsides** | **Heavier and more complex.** Requires **cert-manager** plus the KServe controller (extra pods, CRDs, and webhooks to operate). **Admission-webhook dependency** is a new control-plane coupling: the API server must reach the webhook pods, which made it overlay-sensitive on this cluster (see §3). More abstraction layers to debug; large runtime image pulls; the runtime's arg surface is less transparent than raw vLLM flags. More to go wrong on a small or degraded cluster. |

**Use when:** you operate **many** models or teams, want declarative lifecycle, canary, and
model-format abstraction, and have a healthy cluster to carry the extra control plane.

> **Empirical note (this cluster).** KServe RawDeployment came up and served the model
> cleanly via the huggingface/vLLM runtime, but only after three setup frictions, all
> tied to this cluster: cert-manager webhook pods had to be **co-located with the API
> server** (cordon the laptop) because the broken overlay made them unreachable; the
> cluster resources had to wait for the controller to be Ready; and the runtime's default
> 2Gi `memory` limit collided with the request size. The payoff was that **serving numbers
> were identical to the plain Deployment** (~2,550 vs ~2,600 tok/s on the same vLLM engine),
> so KServe's cost here is **operational, not runtime**. Details and numbers are in
> [real-gpu-results.md §Run 4](gpu-node/real-gpu-results.md).

---

## 2. KServe deployment mode: RawDeployment vs Serverless

KServe itself offers two modes, and the choice is stark on this hardware.

| | RawDeployment (**chosen**) | Serverless |
|---|---|---|
| Stack | Plain K8s `Deployment` + `Service` + HPA | **Knative Serving + Istio/Kourier service mesh** |
| Scale-to-zero | No (HPA min 1) | Yes |
| Resource footprint | Light, just the KServe controller | **Heavy**, a mesh control plane plus per-pod sidecars |
| Networking dependency | Standard Service routing | Leans on the **mesh data plane and pod overlay** |
| Viable on this cluster | :material-check: yes | :material-close: no |

**Decision: RawDeployment.** Serverless would install a service mesh whose data plane
depends on exactly the cross-node pod networking that is **broken under WSL2 mirrored mode**
(§3), and its footprint is overkill for two nodes. Scale-to-zero is nice but not worth
pulling in Knative and Istio here. RawDeployment gives the `InferenceService` abstraction with
ordinary, debuggable Kubernetes primitives.

---

## 3. Traffic plane: ClusterIP Service vs external load balancer

How load reaches the replicas, and the one place the cluster's networking reality leaks
into the design.

### ClusterIP Service (the textbook choice)

| :material-thumb-up: Benefits | :material-thumb-down: Downsides |
|---|---|
| Native K8s load balancing, stable DNS name, zero extra components, dynamic endpoints | Cross-node requests DNAT to a pod IP **on the other node**, which rides the pod overlay. On this cluster that overlay is down, so a Service **cannot spread load across replicas on different nodes**. |

### External nginx LB over node IPs (**chosen for the two-GPU run**)

An nginx round-robin across the two `hostNetwork` node IPs
([vllm-2gpu.yaml](gpu-node/vllm-2gpu.yaml)).

| :material-thumb-up: Benefits | :material-thumb-down: Downsides |
|---|---|
| Works over plain LAN TCP with **no overlay dependency**; simple and observable; load genuinely spreads across both physical GPUs | An extra component to run; node IPs are semi-static (less dynamic than Service endpoints); you own health-checking and config. A **workaround forced by the substrate**, not what you'd choose on a healthy CNI. |

**Decision:** external LB for cross-node fan-out, because it's the only thing that actually
balances across both GPUs given the broken overlay. On a healthy cluster a ClusterIP
Service (or the KServe-managed Service) is the right answer.

---

## 4. Networking substrate: the constraint underneath everything

Every choice above is downstream of one fact: **WSL2 mirrored networking doesn't carry
flannel's kernel-VXLAN overlay between nodes** (full root-cause in the
[troubleshooting log](../docs/cluster-troubleshooting-log.md)). That single constraint is
why this build uses:

- `hostNetwork` and host DNS for serving and exporter pods (pods can't reach CoreDNS or peers across nodes),
- an **external LB** instead of a cross-node ClusterIP Service,
- **co-locating** webhook-backed controllers (cert-manager, KServe) with the API server (cordoning the laptop), since admission webhooks need the API server to reach the webhook pod,
- **RawDeployment** over Serverless (no mesh).

**Production contrast.** A real cluster has a healthy CNI, so none of these workarounds are
needed. ClusterIP Services, KServe Serverless, and a service mesh all just work, and the
networking becomes a performance surface (RDMA/InfiniBand for cross-node tensor
parallelism) rather than a correctness one. The homelab forces the simpler choices, and naming
that gap explicitly is part of the point.

---

## 5. GPU sharing: time-slicing vs MPS vs MIG

Once a card can hold more than one replica, something has to arbitrate access to it.
Three mechanisms exist; only one is available here.

### MIG (Multi-Instance GPU) — **not available**

MIG partitions a supported GPU into hardware-isolated instances, each with its own
memory and compute slice — real isolation, a crashed workload in one instance can't
touch another. It's an Ampere-and-later **datacenter** feature: `nvidia-smi mig -lgip`
reports unsupported on both of this cluster's cards (RTX 3060 Ti, RTX 4070 Laptop —
GeForce/RTX silicon, full stop). No driver version changes that. Ruled out before any
tuning could matter.

### MPS (Multi-Process Service)

Space-partitions memory and compute per client and enforces the limits, closer to
MIG's isolation without the hardware requirement. Needs a control daemon running on
the host and is mutually exclusive with time-slicing in the device plugin's config.
Viable on GeForce, but adds an operational component (the daemon, its lifecycle) this
homelab doesn't otherwise need.

### CUDA time-slicing (**chosen**)

Interleaves compute access to a GPU across replicas with no isolation — one workload
crashing or hogging the card affects everyone sharing it. The trade for that is
simplicity: it's a device-plugin config change
([`nvidia-device-plugin-timeslicing.yaml`](../bootstrap/prereqs/nvidia-device-plugin-timeslicing.yaml)),
no extra daemon, no requirement beyond what the plain device plugin already needs. For
a demo whose point is "does the scheduler let two replicas share this card," the lack
of isolation is an acceptable trade against MPS's extra moving part, especially since
each replica's blast radius (a wedged vLLM process) is already something the
`readinessProbe` and KEDA's health signals are built to catch.

**Decision:** time-slicing, applied optionally alongside the plain (one-`nvidia.com/gpu`-
per-card) device plugin — see
[diy-cluster.md § Sharing a GPU across replicas](gpu-node/diy-cluster.md#sharing-a-gpu-across-replicas-time-slicing)
and [`vllm-timeslice.yaml`](gpu-node/vllm-timeslice.yaml). On hardware with MIG-capable
cards, MIG's isolation would be the better default; time-slicing is the applicable
answer specifically because this fleet is consumer GeForce.

---

## Summary

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| Serving layer | Plain Deployment **and** KServe (both, to compare) | n/a | Plain is fast, simple, and full-control; KServe is platform abstraction at higher cost |
| KServe mode | RawDeployment | Serverless (Knative+Istio) | Serverless mesh depends on the broken overlay and is far heavier |
| Traffic plane | External nginx LB | ClusterIP Service | Cross-node Service routing rides the broken overlay |
| Substrate | `hostNetwork` and host DNS workarounds | Healthy CNI overlay | WSL2 mirrored mode won't carry kernel VXLAN |
| GPU sharing | CUDA time-slicing | MIG (datacenter-only, unavailable) / MPS (needs a control daemon) | Simplest mechanism GeForce hardware actually supports |

The honest through-line: on a constrained cluster, the simplest thing that works beats the
most capable thing that doesn't. Plain Deployment shipped real numbers immediately. KServe
adds platform value but also operational weight, and on degraded networking
that weight shows up as real friction. Knowing when each is worth it is the decision.
