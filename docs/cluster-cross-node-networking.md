# Cross-node pod networking: why it matters

Does the DIY two-GPU cluster actually need **pod-to-pod networking across nodes**, or
is "a GPU pod on each box" enough? This page answers that for the capstone and records
how the cross-node networking blocker found 2026-06-24 was diagnosed and resolved.

- **Cluster runbook (all machines):** [`diy-cluster.md`](../phase-2-capstone/gpu-node/diy-cluster.md)
- **Nodes:** [Windows PC — k3s server](cluster-node-windows-pc.md) · [KAISER-LAPTOP — k3s agent](cluster-node-kaiser-laptop.md)

!!! success "Resolved (2026-06-24): root-caused and worked around"
    Both GPU nodes are `Ready` and advertise `nvidia.com/gpu: 1`, but cross-node
    pod-to-pod traffic failed (server `flannel.1` RX = 0 lifetime). Direct tandem testing
    pinned the root cause: WSL2 mirrored mode does **not** drop generic inbound UDP (plain
    UDP tested 30/30 both ways) — it only delivers inbound UDP to ports with a
    **process-owned userspace socket**, and flannel's VXLAN endpoint on 8472 is an
    **in-kernel** socket (no PID) that the port-mirroring skips, so the overlay never
    enters the peer VM. The two-GPU metrics plane was then unblocked by running the
    exporters with `hostNetwork` and scraping by node IP. Full walk-through:
    [Troubleshooting log](cluster-troubleshooting-log.md).

## 1. Is it needed? By component

The capstone centers on **multi-replica GPU autoscaling**: KEDA
scaling vLLM across two physical GPUs on the KV-cache / TTFT signal
([diy-cluster.md](../phase-2-capstone/gpu-node/diy-cluster.md)). The question isn't
"does Kubernetes need pod networking", it's whether **that specific demo** does. It
splits cleanly:

| Capability needed | Needs cross-node pod networking? | Why |
|---|---|---|
| Schedule 1 vLLM pod onto each GPU node | **No** | The NVIDIA device plugin advertises `nvidia.com/gpu` per node; the scheduler places pods independently of networking. |
| Each vLLM replica serving requests on its own GPU | **No** | Replicas don't talk to each other. Each 8 GB card holds the **whole** model. No cross-node tensor/pipeline parallelism. |
| **Prometheus scraping KV-cache % / TTFT from _both_ GPU pods** | **Yes** | The scrape target is a pod IP on the other node. This **is** the KEDA signal. |
| **Gateway / Service load-balancing requests across both replicas** | **Yes** | A ClusterIP Service DNATs to a backend pod IP that may live on the laptop. |
| CoreDNS + in-cluster Services working for laptop pods | **Yes** | Laptop pods must reach ClusterIP services (CoreDNS, Prometheus) that sit on the desktop. |
| **KEDA scaling on the aggregate signal** | **Yes (transitively)** | It only sees both GPUs if Prometheus could scrape both. |

!!! note "Verdict"
    For the capstone as written, autoscaling vLLM across both physical GPUs on an
    inference-aware signal, **yes, working cross-node pod networking is required.** Not for
    the GPUs themselves, but for the observability and traffic plane that makes two boxes
    behave like one platform. The autoscaling **signal** is exactly what goes blind
    without it: if Prometheus can't scrape the laptop's vLLM pod, KEDA scales on half the
    cluster.

    **This is not a blocker, though.** The single-GPU **Option A** mock already proves the
    KEDA loop ([diy-cluster.md → Reality check](../phase-2-capstone/gpu-node/diy-cluster.md#reality-check));
    the two-GPU cluster is upside, not a dependency.

### How production/enterprise differs

At GitHub-Copilot scale, pod-to-pod networking is **more** central, with a whole tier of
specialized networking layered on top that a home setup deliberately doesn't need:

- **Multi-node model parallelism.** Models too big for one GPU shard across GPUs/nodes
  with NCCL collectives over **RDMA / InfiniBand / NVLink**.
- **Disaggregated prefill/decode** (NVIDIA Dynamo, llm-d). Prefill pods **stream KV cache
  to decode pods across nodes**: heavy, latency-sensitive cross-node pod traffic by design.
- **Service mesh, token-aware gateways, multi-region load balancing**, all built on a
  healthy pod network.

> At small scale pod-to-pod networking serves the control and observability
> plane; at production scale it becomes a first-class performance surface. That's the difference
> between "VXLAN is good enough" and "RDMA or you fail."

---

## 2. The blocker, as first diagnosed

> This section records the **initial** diagnosis. The true root cause (a kernel-socket
> vs. mirrored-mode port-mirroring interaction, not a firewall) was pinned later — see
> [§3](#3-how-it-was-resolved) and the [Troubleshooting log](cluster-troubleshooting-log.md).

Both nodes run WSL2 **mirrored networking** (`.wslconfig`: `networkingMode=mirrored`,
`firewall=true`). The overlay is flannel **VXLAN** (UDP 8472).

**Evidence cross-node traffic fails (collected on the server):**

| Probe | Result | Reading |
|---|---|---|
| Server host → laptop **node** `192.168.18.142` | :material-check: 0% loss, `ttl=128` | `ttl=128` ⇒ the **Windows host** answered, not Linux, confirming mirrored mode |
| Server pod → laptop **pod** (`10.42.1.x`) | :material-close: 100% loss | overlay broken both directions |
| `flannel.1` TX during a 3-ping test | **+3** | desktop **encapsulates and sends** fine (outbound OK) |
| `flannel.1` RX (lifetime) | **0** | **no VXLAN packet has ever been decapsulated**; inbound never arrives |

**Diagnosis.** Outbound works (that's how the agent joined the API server); **inbound
UDP 8472 is not delivered into the remote WSL2 VM**. Two corroborating facts:

- **host-gw is fundamentally incompatible here.** It routes *raw* pod-CIDR packets onto
  the LAN toward the node IP; the Windows host owns that IP and won't route the pod subnet
  into its Linux VM, so the packet dies at the host. VXLAN works *because* it encapsulates
  pod traffic inside UDP-to-node-IP, which mirrored mode delivers. **VXLAN is the correct
  backend.** A brief host-gw experiment on 2026-06-24 was reverted.
- **TCP inbound to the laptop already works.** `kubectl exec` into a laptop pod succeeded,
  which means the API server reaches the laptop kubelet on **TCP 10250**. So the gap is
  **specifically inbound UDP 8472 on the laptop**, a tractable and targeted fix.

The desktop's Hyper-V firewall is already open (`DefaultInboundAction = Allow`, plus
**triplicate** `8472` allow rules, fingerprints of prior fix attempts), so the desktop is
not the blocker. This pointed the investigation at the **laptop** — though the real cause
turned out to be neither host's firewall (see [§3](#3-how-it-was-resolved)).

---

## 3. How it was resolved

The first plan was to chase inbound UDP 8472 on the **laptop** with Hyper-V firewall
rules, on the theory that a missing inbound `Allow` was dropping VXLAN. Direct tandem
testing then disproved it: generic inbound UDP reached the laptop's WSL fine (30/30 both
ways), so the firewall was never the gate. The real cause was structural — mirrored mode
only forwards inbound UDP to **process-owned** sockets, and flannel's VXLAN endpoint is an
in-kernel socket with no owning process, invisible to that port-mirroring.

The fix was to sidestep the overlay for the plane the demo actually needs: run the metrics
exporters (and vLLM) with `hostNetwork` and scrape them by node IP over plain LAN TCP, so
both GPUs report into one Prometheus. The full investigation — the wrong turns and the
one-way tests that killed each theory — is the
[Troubleshooting log](cluster-troubleshooting-log.md), and the real-overlay options
(Tailscale, WSL `bridged` mode) are covered there too.

---

## Appendix: server-side probes used for the diagnosis

Run in the server's WSL2 Ubuntu (as root). Authoritative signal is `flannel.1` RX/TX:

```bash
# VXLAN backend + MTU (1450 = vxlan, 1500 = host-gw):
cat /run/flannel/subnet.env
# VTEP forwarding tables (should list the laptop's VtepMAC -> 192.168.18.142):
bridge fdb show dev flannel.1
ip neigh show dev flannel.1
# Encapsulated send vs decapsulated receive counters:
cat /sys/class/net/flannel.1/statistics/tx_packets
cat /sys/class/net/flannel.1/statistics/rx_packets
```
