# GPU Cluster Node — `KAISER-LAPTOP` (k3s agent)

This machine is a **GPU worker node** in a DIY two-GPU Kubernetes cluster. It runs
**k3s as an _agent_ inside WSL2 Ubuntu** and joins a k3s **server** hosted on an
always-on Windows PC. A MacBook Pro is the **client** (`kubectl` / `helm`,
GitOps/CI); it runs no cluster workloads itself.

- **Cluster runbook (all machines, full steps):** [`diy-cluster.md`](../phase-2-capstone/gpu-node/diy-cluster.md)
- **Companion node:** [Windows PC — k3s server](cluster-node-windows-pc.md)

```text
   Mac (client)              Windows PC (server)        THIS — laptop (agent)
   kubectl + helm   ──API──▶  WSL2 Ubuntu                WSL2 Ubuntu
   GitOps / CI                k3s SERVER + GPU worker     k3s AGENT + GPU worker
                                                          RTX 4070 Laptop, 8 GB
```

> All Kubernetes nodes are **Linux** (WSL2 Ubuntu); the NVIDIA GPU is reached via
> WSL2 GPU passthrough. You never run Kubernetes on Windows directly.

> Specs/state captured 2026-06-23. Re-run [Appendix A](#appendix-a--re-capturing-specs)
> after hardware/driver/OS changes.

---

## 1. Setup status — 2026-06-23

| Step | State |
|------|-------|
| WSL2 + Ubuntu installed | :material-check: done (Ubuntu, WSL version 2) |
| Windows NVIDIA driver + WSL GPU passthrough | :material-check: `nvidia-smi` in WSL lists the RTX 4070 |
| NVIDIA Container Toolkit (in WSL) | :material-check: v1.19.1 |
| Mirrored networking (`.wslconfig`) | :material-check: verified — WSL `hostname -I` == host `192.168.18.140` |
| **k3s agent — joined to the PC server** | :material-timer-sand: **pending** — needs the PC server's LAN IP + node-token |
| NVIDIA device plugin (advertise `nvidia.com/gpu`) | :material-timer-sand: pending (after join) |

What remains is **only the join** — see [§5](#5-remaining-steps--join-the-cluster).
It is blocked until the PC k3s server exists.

---

## 2. Hardware & OS specs

| Component | Detail |
|-----------|--------|
| **Make / model** | Acer Predator PH16-71 (laptop) |
| **Hostname** | `KAISER-LAPTOP` |
| **OS** | Windows 11 Home, version 10.0.26200 (build 26200), 64-bit |
| **CPU** | Intel Core i7-13700HX (13th Gen) — 16 cores / 24 threads, 2.1 GHz base |
| **RAM** | 16 GB (15.7 GiB usable) |
| **Storage** | Micron 3400 NVMe SSD, ~1 TB (954 GB) |
| **Discrete GPU** | **NVIDIA GeForce RTX 4070 Laptop GPU** |
| **Integrated GPU** | Intel UHD Graphics (iGPU — ignore for compute) |

### GPU details (the part that matters)

| GPU property | Value |
|--------------|-------|
| Device | NVIDIA GeForce RTX 4070 Laptop GPU |
| VRAM | **8 GB GDDR6** (8188 MiB reported by `nvidia-smi`) |
| Power cap | 55 W (laptop TGP-limited) |
| Driver version | 596.36 (Windows; provides the WSL CUDA stack) |
| CUDA driver capability | **CUDA 13.2** (max version the driver supports) |
| Compute capability | 8.9 (Ada Lovelace, `sm_89`) |
| GPU UUID | `GPU-12a01891-28e9-a7f2-df85-e3145dc0e261` |
| WDDM mode | Yes (consumer/laptop driver model) |

**Cluster-planning caveats:**

- **8 GB VRAM is the binding constraint for the whole cluster.** Kubernetes sizes
  by `nvidia.com/gpu` count, not VRAM, so the model that lands on *both* nodes must
  fit the **smaller** card — this one. Plan workloads around 8 GB even if the PC has
  more (see [§4](#4-model-sizing-constraint)).
- **55 W TGP** means sustained throughput is well below a desktop 4070. Expect
  thermal throttling on long runs; keep the laptop plugged in and on a hard surface.
- **WDDM driver model** (not TCC) — normal for laptop NVIDIA GPUs. The desktop
  compositor always reserves a little VRAM. The GPU still passes through to WSL2 and
  to containers via the NVIDIA Container Toolkit.

---

## 3. Network state

| Setting | Value |
|---------|-------|
| Active interface | **Wi-Fi** — Killer Wi-Fi 6E AX1675i |
| Current IPv4 | `192.168.18.140` (Wi-Fi MAC `56-D5-10-EC-9C-FC`) |
| Subnet / gateway | `192.168.18.0/24`, gateway `192.168.18.1` |
| Workgroup | `WORKGROUP` (not domain-joined) |
| Ethernet | Present but unplugged (self-assigned `169.254.x.x`) |
| **WSL2 networking** | **Mirrored** — WSL shares the host IP `192.168.18.140` on the LAN |

**Mirrored networking is the key enabler.** By default WSL2 sits behind NAT and its
Linux IP isn't reachable from the LAN, which breaks multi-host k3s. The `.wslconfig`
on this machine sets `networkingMode=mirrored`, so the k3s agent in WSL is reachable
from the PC server and Mac at the host's LAN IP. Verified: `hostname -I` inside WSL
returns `192.168.18.140`, the same address Windows uses.

**Give this node a stable IP.** k3s and the agent don't care which IP, but a DHCP
lease change after reboot is one less surprise. In the router (`http://192.168.18.1`)
bind MAC `56-D5-10-EC-9C-FC` to a fixed IP, or set a static IP in Windows. **Wired
Ethernet** to the same switch as the PC is worth it for a compute node — lower
latency and far steadier than shared Wi-Fi.

---

## 4. Model sizing constraint

The deployed vLLM model must fit the **smaller of the two GPUs**, which is this
laptop's **8 GB**. Good fits for 8 GB (weights + KV cache + overhead):

- **3B–4B at FP16** (~6–8 GB) — comfortable, room for KV cache.
- **7B–8B quantized** (AWQ / GPTQ INT4, ~5–6 GB weights) — fits with usable KV cache.
- Avoid 7B+ at FP16 (~14 GB+) — won't fit.

Start with `Qwen/Qwen2.5-3B-Instruct` (FP16) or a 7B-AWQ build, and set
`--gpu-memory-utilization 0.90 --max-model-len 4096`.

---

## 5. Remaining steps — join the cluster

Everything below is blocked on the **PC k3s server** existing. Once it's up, you'll
have its **LAN IP** and **node-token** (`sudo cat /var/lib/rancher/k3s/server/node-token`
on the PC). Then, in this laptop's WSL2 Ubuntu:

```bash
# 1) Join as a k3s agent
curl -sfL https://get.k3s.io | K3S_URL=https://<PC-LAN-IP>:6443 \
  K3S_TOKEN=<token-from-server> sh -

# 2) Point k3s's bundled containerd at the NVIDIA runtime, then advertise the GPU
sudo nvidia-ctk runtime configure --runtime=containerd \
  --config=/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl
sudo systemctl restart k3s-agent
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.16.2/deployments/static/nvidia-device-plugin.yml
```

From the **Mac**, confirm this node appears and advertises a GPU:

```bash
kubectl get nodes -o wide        # KAISER-LAPTOP should be Ready
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'
# this node should report 1 GPU
```

Full multi-machine procedure (PC server install, firewall ports, deploy across both
GPUs) is in [`diy-cluster.md`](../phase-2-capstone/gpu-node/diy-cluster.md).

> **Keep the node awake during runs.** If the laptop sleeps, its node goes
> `NotReady` and pods reschedule. Plug in, set High Performance, and disable sleep
> (Admin PowerShell): `powercfg /change standby-timeout-ac 0`.

---

## 6. Optional — direct SSH access (admin convenience, not the cluster path)

The cluster control path is **k3s over the LAN**, not SSH — the Mac drives the
cluster with `kubectl`, not by shelling into this box. SSH is only worth setting up
if you want a remote terminal for housekeeping. If so (Admin PowerShell):

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd; Set-Service -Name sshd -StartupType Automatic
```

`nvidia-smi` (ships with the driver, works in Windows and WSL) is the quick local
GPU check; in-cluster GPU metrics come from Prometheus scraping the workload, not
from SSH.

---

## Appendix A — re-capturing specs

Refresh this doc after changes. On Windows (PowerShell):

```powershell
Get-CimInstance Win32_ComputerSystem | Select Manufacturer,Model,TotalPhysicalMemory,Name,Workgroup
Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
Get-CimInstance Win32_OperatingSystem | Select Caption,Version,BuildNumber,OSArchitecture
nvidia-smi
Get-NetIPConfiguration | ? {$_.IPv4Address}
Get-NetAdapter | ? Status -eq 'Up' | Select Name,InterfaceDescription,LinkSpeed,MacAddress
```

Inside WSL2 Ubuntu (verifies passthrough + mirrored networking + cluster bits):

```bash
nvidia-smi -L                 # GPU visible to Linux
nvidia-ctk --version          # container toolkit
hostname -I                   # should match the Windows LAN IP (mirrored mode)
wsl.exe -l -v                 # (from PowerShell) distro + WSL version
sudo k3s kubectl get nodes    # once joined
```
