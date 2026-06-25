# Cross-node pod networking: why it matters and current status

Does the DIY two-GPU cluster actually need **pod-to-pod networking across nodes**, or
is "a GPU pod on each box" enough? This page answers that for the capstone, records the
networking blocker found 2026-06-24, and lays out the next steps on the laptop.

- **Cluster runbook (all machines):** [`diy-cluster.md`](../phase-2-capstone/gpu-node/diy-cluster.md)
- **Nodes:** [Windows PC — k3s server](cluster-node-windows-pc.md) · [KAISER-LAPTOP — k3s agent](cluster-node-kaiser-laptop.md)

!!! warning "Status (2026-06-24): cross-node pod overlay is **not** passing traffic"
    Both GPU nodes are `Ready` and each advertises `nvidia.com/gpu: 1`, but **cross-node
    pod-to-pod traffic fails** (server `flannel.1` RX = 0 lifetime). Node `Ready` only
    means the agent's kubelet reaches the API server outbound. It does **not** prove
    the pod overlay works. This is a WSL2 mirrored-mode inbound delivery problem, not a
    flannel backend choice. Details in [§2](#2-current-status--the-blocker).

!!! success "Resolved (2026-06-24): root cause found + metrics unblocked"
    Direct tandem testing later pinned the **actual** root cause, which refines the note
    above. Mirrored mode does **not** drop generic inbound UDP (plain UDP tested 30/30 both
    ways). It only delivers inbound UDP to ports with a **process-owned userspace socket**,
    and flannel's VXLAN endpoint on 8472 is an **in-kernel** socket (no PID) that the
    port-mirroring skips, so the overlay never enters the peer VM. The two-GPU metrics
    plane was then unblocked by running the exporters with `hostNetwork` and scraping by
    node IP. Full details: [Troubleshooting log](cluster-troubleshooting-log.md).

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

## 2. Current status: the blocker

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
not the blocker. Attention now turns to the **laptop**.

---

## 3. Next steps: laptop side

Run these on the **laptop** (`KAISER-LAPTOP`, `192.168.18.142`). The goal: get inbound
UDP 8472 delivered into its WSL2 VM so flannel can decapsulate.

### Step 1: verify the laptop's WSL firewall (Windows PowerShell, Admin)

```powershell
# WSL Hyper-V firewall defaults (mirrored mode routes WSL traffic through this):
Get-NetFirewallHyperVVMSetting -PolicyStore ActiveStore |
  Select-Object Name, DefaultInboundAction, DefaultOutboundAction

# Existing rules for the k3s ports:
Get-NetFirewallHyperVRule |
  Where-Object { $_.DisplayName -match '8472|6443|10250|flannel|k3s' } |
  Select-Object DisplayName, Direction, Action
```

If there is **no inbound Allow for UDP 8472**, that's the most likely cause.

### Step 2: add the inbound UDP 8472 rule (Windows PowerShell, Admin)

`{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}` is WSL's fixed Hyper-V VM-creator ID.

```powershell
New-NetFirewallHyperVRule -Name "k3s-flannel-vxlan-8472" `
  -DisplayName "k3s flannel VXLAN 8472" -Direction Inbound `
  -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -Protocol UDP -LocalPorts 8472 -Action Allow
```

(6443/TCP and 10250/TCP are already working, since the agent joined and `kubectl exec`
succeeded, so they need no change. Add them the same way only if Step 1 shows them missing.)

### Step 3: isolate UDP delivery (only if Step 2 doesn't fix it)

Confirms whether *any* inbound UDP reaches the laptop's WSL, or it's a deeper mirrored-mode
limitation. Run the listener on the **laptop WSL**, send from the **desktop WSL**:

```bash
# Laptop WSL (listener):
python3 -c "import socket;s=socket.socket(2,2);s.bind(('0.0.0.0',51888));print(s.recvfrom(2048))"
# Desktop WSL (sender):
echo HELLO | nc -u -w1 192.168.18.142 51888
```

- **Arrives** → generic UDP inbound works; the issue was VXLAN/8472-specific (firewall).
- **Nothing** → mirrored-mode isn't delivering inbound UDP at all. Try `firewall=false` in
  the laptop's `.wslconfig` plus `wsl --shutdown` as a test; if that's still dead, treat
  cross-node overlay as not viable on this setup and **fall back to single-GPU Option A**.

### Step 4: verify the fix from the server

After the laptop change (and `wsl --shutdown` if you edited `.wslconfig`, which restarts
k3s), re-test on the **server**:

```bash
# RX should now climb when laptop pods send across (was stuck at 0):
cat /sys/class/net/flannel.1/statistics/rx_packets
# Then a real cross-node pod-to-pod ping should reach 0% loss
# (schedule one busybox pod per node via nodeName and ping pod IP to pod IP).
```

When `flannel.1` RX increments and a cross-node pod ping succeeds, the overlay is healthy
and the two-GPU KEDA autoscaling demo is unblocked.

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
