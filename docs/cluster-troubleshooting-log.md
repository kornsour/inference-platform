# Troubleshooting log: cracking cross-node GPU networking

A debugging case study. Two GPU machines joined into one k3s cluster, both nodes
`Ready`, both advertising a GPU, yet the cross-node pod overlay silently passed zero
traffic. This walks through the wrong turns, the experiments that reframed the
problem, the root cause, and the fix. I keep it as a runbook, and because the method
for cornering a bug like this is the real takeaway.

!!! success "TL;DR"
    **Symptom:** cross-node pod-to-pod traffic 100% lost; `flannel.1` RX stuck at `0`
    lifetime on both nodes, even though nodes were `Ready` and TCP between them worked.

    **Three wrong theories**, each disproven with a targeted test: host firewall, the
    flannel backend choice (`host-gw`), and UDP checksum offload.

    **Root cause:** WSL2 *mirrored networking* only delivers inbound UDP to ports backed
    by a **process-owned userspace socket**. flannel's VXLAN endpoint on UDP 8472 is an
    **in-kernel** socket with no owning process, so encapsulated packets leave the sender
    but are never handed to the peer VM.

    **Fix:** run the metrics pods with `hostNetwork: true` and scrape them on the node IP
    over TCP. This sidesteps the overlay for the observability plane the autoscaling
    demo actually needs. Both GPUs end up reporting into one Prometheus.

---

## 1. What I was building

The capstone's headline is real multi-replica GPU autoscaling: KEDA scaling vLLM
across two physical GPUs (a desktop RTX 3060 Ti and a laptop RTX 4070) on an
inference-aware signal. That needs Prometheus to scrape inference and GPU metrics from pods
on both machines. The scrape target is a pod on the other node, so it depends on
the cross-node pod network working. (Full rationale:
[cross-node networking](cluster-cross-node-networking.md).)

| Machine | Role | GPU | WSL2 |
|---|---|---|---|
| `kaiser-desktop` (`192.168.18.2`) | k3s **server** + GPU worker | RTX 3060 Ti, 8 GB | mirrored |
| `kaiser-laptop` (`192.168.18.142`) | k3s **agent** + GPU worker | RTX 4070 Laptop, 8 GB | mirrored |
| MacBook Pro | client: `kubectl`, orchestration | — | — |

Both run Kubernetes inside **WSL2 Ubuntu** with **mirrored networking**
(`networkingMode=mirrored`), which is what puts each WSL instance on the LAN so the two
can cluster at all. The overlay is flannel VXLAN (UDP 8472).

---

## 2. The symptom, and why "Ready" lied

Both nodes showed `Ready`. That is a trap: `Ready` only means the agent's kubelet can
reach the API server **outbound**. It says nothing about the pod overlay.

The authoritative signal is the VXLAN device counter:

```bash
cat /sys/class/net/flannel.1/statistics/tx_packets   # climbing, sends fine
cat /sys/class/net/flannel.1/statistics/rx_packets   # 0, NEVER received one
```

`TX` climbing + `RX` stuck at `0`, on **both** nodes, lifetime. Packets were being
encapsulated and sent, and nothing was ever decapsulated on the other side.

---

## 3. The wrong turns (and how each was killed)

Good debugging isn't avoiding wrong theories. It's killing them quickly with a test that
can only come out one way.

### :material-close: Theory 1: the firewall is blocking UDP 8472

The most popular WSL2 answer online. Over prior sessions I had already added the
standard firewall rule, a Hyper-V firewall rule, flipped the Hyper-V default-inbound to
`Allow`, and toggled checksum offload. Four firewall avenues, no change.

This session I confirmed it cold from inside both VMs:

- Hyper-V VM firewall: `DefaultInboundAction = Allow`, plus *explicit* inbound `Allow`
  rules for 8472 (two of them on the laptop).
- Standard host Defender firewall: default inbound effectively `Block`, but it doesn't
  govern here, because brand-new TCP ports into WSL (SSH on 2222, kubelet 10250, API
  6443) all connected fine with no rule added.

**Verdict:** if arbitrary inbound TCP reaches WSL with the firewall untouched, the
firewall is not what's eating VXLAN. Killed.

### :material-close: Theory 2: wrong flannel backend, switch to `host-gw`

Tempting because `host-gw` drops VXLAN entirely and just uses IP routing. But it's
architecturally doomed here. `host-gw` puts a route on each host pointing the pod CIDR
at the other node's IP, and under mirrored mode the Windows host owns that IP and
won't route a foreign pod subnet into its Linux VM. A brief experiment confirmed it, then
I reverted. VXLAN is in fact the correct backend for this topology. Killed.

### :material-close: Theory 3: VXLAN packets have bad UDP checksums

This one looked extremely promising. A packet capture of the encapsulated traffic showed:

```
192.168.18.2.48366 > 192.168.18.142.8472: [bad udp cksum 0xa664 -> 0xf1c6!] VXLAN, vni 1
```

"Bad checksum" is a classic flannel-on-virtualized-NIC failure: offload sets
`CHECKSUM_PARTIAL` expecting hardware to finish it, and the virtual path never does. So I
disabled the offload:

```bash
ethtool -K flannel.1 tx-checksum-ip-generic off   # no change
ethtool -K eth1 tx off                            # no change (and broke tx entirely)
```

No effect on `RX`. On closer reading, that `bad cksum` line was a **tcpdump artifact**
of capturing a locally-generated packet *before* offload. The VXLAN device also uses a
zero outer checksum by default, which receivers don't validate. I reverted both
changes. Killed.

!!! note "The lesson hiding here"
    A plausible cause with a real-looking piece of evidence (`bad udp cksum`) was still
    wrong. The discipline that saved time: **change one thing, measure the authoritative
    counter, revert if it doesn't move.** Don't let a good story outrun the data.

---

## 4. The move that cracked it: direct, tandem access

The real blocker to progress was methodology. The cross-node test is a paired
listener/sender, and relaying commands by hand to two machines meant the send and listen
windows never lined up. Every "0 received" was ambiguous.

So I changed the setup: stand up SSH **directly into both WSL instances** (port 2222,
key-only, locked to the Mac's IP) and drive both from one place, exactly like SSHing into
two EC2 boxes. Now a single script could open both listeners, fire both senders to the
millisecond, and collect results centrally.

The first synchronized experiment reframed the entire problem:

```text
DESKTOP listener  ← LAPTOP sent 30:  TOTAL_RECEIVED 30
LAPTOP  listener  ← DESKTOP sent 30: TOTAL_RECEIVED 30
```

**Plain UDP between the two WSL instances works perfectly, both directions, 30/30.** The
entire "mirrored mode drops inbound UDP" premise, the thing four firewall attempts were
chasing, was **false**. Generic UDP is fine. So what's different about VXLAN?

---

## 5. Isolating the real variable

A packet capture on the receiver, filtered per direction, showed the brutal truth:

| Direction | Sent | Arrived at peer |
|---|---|---|
| desktop → laptop (VXLAN :8472) | 8 | **0** |
| laptop → desktop (VXLAN :8472) | 72 | **0** |

Packets left (TX climbed) and **never arrived**. Yet identical plain UDP on :51888 hit
30/30. Same hosts, same `eth1`, same protocol. The only differences were the destination
port and *what created the socket*.

Then a methodology check caught a subtlety that reframed it one more time. A capture with
**no bound listener** showed `0` even for the known-good :51888, but a capture **with** a
listener bound showed the packets arriving. Run side by side:

```text
bound listener on :51888  → received 8
tcpdump on :51888 alone   → 0   (until a socket is bound, nothing is delivered)
```

That's the tell. **WSL2 mirrored mode delivers inbound UDP into the VM only for ports
that have a bound, process-owned socket.** It mirrors *listening ports*.

And what kind of socket does flannel's VXLAN use?

```bash
ss -uanp | grep 8472
# UNCONN  0  0  0.0.0.0:8472  0.0.0.0:*        <-- note: NO owning process
```

A userspace listener shows up with its PID. The VXLAN endpoint is an **in-kernel** socket
with **no owning process**, invisible to the port-mirroring that decides what inbound
traffic to forward.

---

## 6. Root cause

!!! danger "Root cause"
    Under **WSL2 mirrored networking**, inbound UDP is only delivered to the VM for ports
    backed by a **process-owned userspace socket**. flannel's VXLAN overlay terminates on
    an **in-kernel** UDP socket (port 8472, no PID), so encapsulated cross-node packets are
    sent by the source (`flannel.1` TX rises) but **never handed to the destination VM**
    (`flannel.1` RX = 0 forever). It is not a firewall, not the backend choice, and not
    checksums. It is a structural interaction between mirrored-mode port mirroring and
    kernel-terminated overlays.

This also cleanly explains why several "obvious" fixes can't work:

| Attempted / tempting fix | Why it can't work here |
|---|---|
| Open more firewall rules | Generic inbound UDP/TCP already arrive; firewall isn't the gate |
| `host-gw` backend | Windows host won't route the pod CIDR into the VM |
| Change the VXLAN port off 8472 | *Any* kernel VXLAN socket has the same no-PID problem |
| k3s `--flannel-backend=wireguard-native` | Kernel WireGuard is also a kernel socket, same trap |

---

## 7. The fix: sidestep the overlay for the plane that matters

The autoscaling demo doesn't actually need a healthy pod overlay. It needs Prometheus to
reach the GPU and inference metrics on both nodes. Those are TCP, and TCP to a
process-owned port already works. So run the exporter with `hostNetwork: true`: its pod IP
becomes the node IP on a real userspace socket, and the existing PodMonitor scrapes it
over the LAN.

```bash
kubectl -n monitoring patch ds nvidia-gpu-exporter --type merge \
  -p '{"spec":{"template":{"spec":{"hostNetwork":true,"dnsPolicy":"ClusterFirstWithHostNet"}}}}'
```

Before → after, straight from the cluster-wide Prometheus (which runs on the laptop, so the
desktop exporter is the cross-node hop):

```text
BEFORE:  DOWN  http://10.42.0.39:9835/metrics   context deadline exceeded   <- desktop pod IP, cross-node
         UP    http://10.42.1.37:9835/metrics                               <- laptop, same node

AFTER:   UP    http://192.168.18.2:9835/metrics                             <- desktop NODE IP
         UP    http://192.168.18.142:9835/metrics                           <- laptop  NODE IP
```

Both physical GPUs now report into one Prometheus:

```text
node 192.168.18.2:9835    GPU: NVIDIA GeForce RTX 3060 Ti
node 192.168.18.142:9835  GPU: NVIDIA GeForce RTX 4070 Laptop GPU
```

That is the aggregate, two-GPU signal KEDA scales on, delivered without fighting WSL.

!!! note "Same fix applies to vLLM"
    The vLLM [`podmonitor.yaml`](../phase-2-capstone/k8s/podmonitor.yaml) scrapes by pod
    IP too, so a multi-node vLLM deployment will hit the identical wall. Give those pods
    `hostNetwork` (or scrape them by node IP) and the autoscaling signal stays whole.

---

## 8. If you want a real pod overlay (not just a sidestep)

The `hostNetwork` fix unblocks the capstone. If you want genuine cross-node pod-to-pod
networking, the root cause points straight at the answer: **the overlay must ride a
process-owned userspace socket.**

- **Tailscale** (`k3s --vpn-auth`): `tailscaled` is a userspace daemon (its socket *is*
  forwarded), and it falls back to a DERP relay over TCP/443 if direct UDP fails. Given
  TCP already works here, this connects even in the worst case. This is the recommended
  real-overlay path.
- **WSL `networkingMode=bridged`**: gives each WSL its own LAN NIC, bypassing mirrored-mode
  port mirroring entirely, so kernel VXLAN works normally. Cleanest, but needs Hyper-V and
  wired Ethernet (bridging over Wi-Fi is unreliable).

---

## 9. Transferable habits

Separated from the WSL specifics:

- **Distrust green checkmarks.** `Ready` nodes hid a dead data plane. Find the
  authoritative low-level signal (`flannel.1` RX) and watch that, not the dashboard.
- **Kill theories with one-way tests.** Firewall, backend, and checksum were each ended by
  a single experiment whose result couldn't be argued with.
- **Verify the measurement, not just the result.** The breakthrough came from noticing the
  tool (tcpdump without a bound socket) was lying. The bug was partly in how I was
  looking.
- **Isolate one variable.** Plain UDP vs VXLAN, bound vs unbound socket. Each comparison
  removed half the search space.
- **Get the right access early.** Direct tandem SSH turned an ambiguous, hand-relayed test
  into a deterministic one and collapsed days of guessing into an afternoon.
- **Know when to fix vs. sidestep.** The goal was a working autoscaling signal, not a
  philosophically pure overlay. `hostNetwork` shipped the outcome today, and Tailscale
  remains available for the overlay itself.
