# Tech stack: what, why, and the trade-offs

This page lists every component in the platform and the reasoning behind it: what it is for, what I chose it over, the trade-off it carries, and the benefit it buys. The contested calls (plain Deployment vs KServe, the traffic plane, the WSL2 substrate) get deeper treatment in [architecture decisions](architecture-decisions.md). This page is the at-a-glance justification for the whole stack.

The through-line is that every choice trades complexity for capability. On a constrained homelab cluster I biased toward the simplest thing that works, but the heavier production-grade options (KServe, Argo CD, Envoy) are present too, so the trade-off is demonstrable rather than theoretical.

## Cluster and substrate

| Choice | Why | Chosen over | Trade-off |
|---|---|---|---|
| **k3s** | Lightweight CNCF Kubernetes, single binary, runs on consumer hardware; same API as EKS so skills transfer | kubeadm, EKS | Fewer batteries included; some add-ons need manual wiring |
| **WSL2 + GPU passthrough** | Real Linux Kubernetes on existing Windows GPU boxes for $0 | Dual-boot Linux, cloud GPUs | Mirrored-mode overlay breakage (the entire [troubleshooting saga](../docs/cluster-troubleshooting-log.md)) |
| **flannel (VXLAN)** | k3s default CNI; correct backend for this topology | Cilium, Calico, host-gw | Kernel-VXLAN socket isn't delivered under WSL2 mirrored mode, forcing `hostNetwork` workarounds everywhere |

**Benefit:** genuine multi-node GPU Kubernetes for $0 on hardware I already owned, plus a hard-won understanding of the CNI layer most people treat as a black box.

## Serving engine and model server

| Choice | Why | Chosen over | Trade-off |
|---|---|---|---|
| **vLLM** | SOTA throughput via PagedAttention and continuous batching; OpenAI-compatible; emits the exact KV-cache and queue metrics autoscaling needs | TGI, TensorRT-LLM, SGLang | Python/CUDA footprint; consumer-GPU VRAM ceilings (3B barely fits 8 GB) |
| **KServe** | Standard `InferenceService` CRD, model-format abstraction, canary, multi-model consistency | Plain Deployment *(also built, to compare)*, Ray Serve, Seldon | Heavier control plane; webhook- and overlay-sensitive |

**Benefit:** real engine behavior (true KV-cache metrics, continuous batching) plus a side-by-side of the hand-rolled and platform approaches. See the [results](gpu-node/real-gpu-results.md) and [trade-offs](architecture-decisions.md).

## Autoscaling

| Choice | Why | Chosen over | Trade-off |
|---|---|---|---|
| **KEDA** | Scale on **arbitrary Prometheus metrics** (queue depth, KV-cache), not just CPU/RPS; scale-to-zero | Raw HPA (CPU only), Knative/KPA (concurrency only) | Another controller plus admission webhook |
| **Custom Go external scaler** | One composite signal, `max(queue/threshold, kv/threshold)`, that a single PromQL trigger can't express | Two built-in prometheus triggers *(also provided)* | Code to maintain plus an image to ship |

**Benefit:** inference-aware autoscaling, the platform's core differentiator, proven on real GPUs where the 3B model drives KV-cache to 99.5% and trips the signal.

## Observability

| Choice | Why | Chosen over | Trade-off |
|---|---|---|---|
| **Prometheus + Grafana** | De-facto CNCF metrics and dashboards; both KEDA and vLLM speak Prometheus natively | Datadog / cloud (cost), VictoriaMetrics | Operator complexity; needed a `hostNetwork` patch here |
| **nvidia_gpu_exporter** | Parses `nvidia-smi`, which works under WSL2 where DCGM is flaky on consumer GeForce | NVIDIA DCGM exporter | Fewer fields than DCGM |
| **cert-manager** | TLS for the KServe and KEDA webhooks (a dependency, not a choice per se) | Hand-managed certs | One more controller and webhook to operate |

**Benefit:** one Prometheus is the shared substrate for dashboards, the SLO and alert, and the autoscaling signal, using the same metric names from mock to GPU.

## Traffic plane

| Choice | Why | Chosen over | Trade-off |
|---|---|---|---|
| **nginx LB** | Dependency-free cross-node load balancing over node IPs that works without the overlay | ClusterIP Service (broken cross-node here) | Static config, manual health-checking |
| **Envoy AI Gateway** | Token-aware routing, rate limiting, model-name dispatch, and multi-backend failover: the production OpenAI front door | App-level routing, a plain API gateway | The heaviest, most overlay-sensitive layer (automated in the bootstrap, not live-validated on this cluster) |

**Benefit:** the LB proves cross-node fan-out today, and the gateway scaffolds the production-grade traffic management you would run at scale.

## Delivery: IaC, GitOps, CI

| Choice | Why | Chosen over | Trade-off |
|---|---|---|---|
| **Bootstrap scripts (Bash + Make)** | One-command spin-up and teardown that encodes the install order and every WSL2 workaround; zero deps, fully transparent | Terraform, Helmfile | Less declarative than Terraform, chosen for transparency and no extra tooling |
| **Argo CD** | Declarative GitOps CD with auto-sync, self-heal, and prune; CNCF graduated | Flux, plain `kubectl apply` | Another control plane to run |
| **GitHub Actions** | Repo-native CI: lint, schema-validate manifests, then build and test the Go scaler | Jenkins, GitLab CI | Some vendor coupling |

**Benefit:** the platform reconstitutes from a clean clone for a demo, deploys are declarative and self-healing, and nothing merges without validation.

## Languages

| Language | Used for | Why it (not the alternative) | Trade-off |
|---|---|---|---|
| **Go** | The KEDA external scaler | The Kubernetes-ecosystem lingua franca; gRPC plus a static distroless binary; the right fit for code that integrates with the control plane | More ceremony than Python for a small service |
| **Python** | vLLM, the metrics-faithful mock, the load generator | Fastest iteration; the ML and serving ecosystem; dependency-free stdlib tools | Runtime weight vs a compiled binary |
| **Bash + Makefile** | Bootstrap and teardown glue | Transparent, universal, no install step, so you can read exactly what it does to your cluster | Less structured than a Go/Python CLI |
| **YAML** | All Kubernetes manifests | The platform's declarative substrate; what Argo reconciles | Verbose and logic-free (intentionally, since logic lives in controllers, not templates) |

**Benefit:** the right tool per layer. Compiled Go where it integrates with the Kubernetes control plane, Python where iteration speed wins, and declarative YAML for desired state.
