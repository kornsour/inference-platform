# GPU Cluster Node — `KAISER-DESKTOP` (k3s server)

The **always-on Windows PC** is the **k3s server** and a GPU worker in the DIY
two-GPU cluster. Because the control plane must stay reachable, the API lives here.
The [laptop](cluster-node-kaiser-laptop.md) joins as an agent, and the MacBook Pro
is the **client** (`kubectl` / `helm`, GitOps/CI).

- **Cluster runbook (all machines, full steps):** [`diy-cluster.md`](../phase-2-capstone/gpu-node/diy-cluster.md)
- **Companion node:** [KAISER-LAPTOP — k3s agent](cluster-node-kaiser-laptop.md)

```text
   Mac (client)              THIS — Windows PC (server)   Windows laptop (agent)
   kubectl + helm   ──API──▶  WSL2 Ubuntu                 WSL2 Ubuntu
   GitOps / CI                k3s SERVER + GPU worker      k3s AGENT + GPU worker
   KAISER-DESKTOP             RTX 3060 Ti, 8 GB            RTX 4070 Laptop, 8 GB
```

> All Kubernetes nodes are **Linux** (WSL2 Ubuntu). The NVIDIA GPU is reached via
> WSL2 GPU passthrough. You never run Kubernetes on Windows directly.

> **k3s server is live (2026-06-23)** at `192.168.18.2`; the laptop agent has joined
> and both nodes advertise a GPU. Specs/state captured 2026-06-23. Re-run
> [Appendix A](#appendix-a-capturing-specs) after hardware/driver/OS changes.

---

## 1. Setup status — 2026-06-23

| Step | State |
|------|-------|
| WSL2 + Ubuntu installed | :material-check: done (Ubuntu 26.04 LTS, WSL 2.6.1.0, systemd on) |
| Windows NVIDIA driver + WSL GPU passthrough | :material-check: `nvidia-smi -L` in WSL lists the RTX 3060 Ti |
| NVIDIA Container Toolkit (in WSL) | :material-check: done: `nvidia-ctk` v1.19.1 |
| Mirrored networking (`.wslconfig`) | :material-check: done: WSL `hostname -I` == host `192.168.18.2` |
| **k3s server installed** | :material-check: done: v1.35.5+k3s1, node `kaiser-desktop` `Ready` (control-plane), internal IP `192.168.18.2` |
| Firewall: 6443/TCP, 8472/UDP, 10250/TCP open on the LAN | :material-check: done: 3 inbound rules scoped to `192.168.18.0/24`; flannel VXLAN established |
| NVIDIA device plugin (advertise `nvidia.com/gpu`) | :material-check: done: node reports `nvidia.com/gpu: 1`; validated with a `runtimeClassName: nvidia` pod running `nvidia-smi -L` (saw the 3060 Ti) |
| LAN IP + node-token handed to the laptop & Mac | :material-check: laptop joined (`192.168.18.142`), advertising `nvidia.com/gpu` · :material-timer-sand: Mac kubeconfig pending |

This node is **fully up**: k3s server `Ready`, GPU advertised and validated end to
end. The [laptop](cluster-node-kaiser-laptop.md) has since **joined** with this
server's IP + token, so both GPUs are now in the cluster. What remains is handing the
[Mac](#4-setup-steps-this-machine) a kubeconfig.

> **GPU-advertise gotcha (hit on 2026-06-23):** do **not** run
> `nvidia-ctk runtime configure --config=…/config.toml.tmpl` against k3s. It
> overwrites k3s's containerd template and drops the flannel CNI config, leaving the
> node `NotReady` (`cni plugin not initialized`). k3s **auto-detects** the NVIDIA
> Container Toolkit at startup and creates a `nvidia` `RuntimeClass` on its own. The
> working recipe is in [§4 step 5](#4-setup-steps-this-machine).

---

## 2. Hardware & OS specs

| Component | Detail |
|-----------|--------|
| **Make / model** | Custom desktop (MSI MS-7C91 / B550 motherboard) |
| **Hostname** | `KAISER-DESKTOP` |
| **OS** | Windows 11 Pro, version 10.0.26200 (build 26200), 64-bit |
| **CPU** | AMD Ryzen 5 5600X (6 cores / 12 threads) |
| **RAM** | 32 GB (31.9 GiB usable) |
| **Storage** | Samsung 990 PRO 2 TB NVMe (primary) + 860 EVO 1 TB + 850 EVO 250 GB (SATA SSDs) |
| **Discrete GPU** | **NVIDIA GeForce RTX 3060 Ti** |
| **WSL distro** | Ubuntu 26.04 LTS (kernel 6.6.87.2), default user `ajkai`, systemd enabled |

### GPU details (the part that matters)

| GPU property | Value |
|--------------|-------|
| Device | NVIDIA GeForce RTX 3060 Ti |
| VRAM | **8 GB GDDR6** (8192 MiB reported by `nvidia-smi`) |
| Power cap | 200 W (desktop card, full TGP) |
| Driver version | 591.86 (Windows; provides the WSL CUDA stack) |
| CUDA driver capability | **CUDA 13.1** (max version the driver supports) |
| Compute capability | 8.6 (Ampere, `sm_86`) |
| GPU UUID | `GPU-0129195d-5d3e-0b2e-9f35-e17ef08e538f` |
| WDDM mode | Yes (consumer driver model) |

**Cluster-planning notes:**

- **8 GB VRAM, same as the laptop, so the cluster ceiling is unchanged.** Both
  nodes are 8 GB, so the model that lands on *both* still targets 8 GB
  (see [§4 of the laptop doc](cluster-node-kaiser-laptop.md#4-model-sizing-constraint)).
  The original plan assumed a 12 GB PC card. The actual card is 8 GB, which simply
  keeps the existing 8 GB sizing.
- **Full 200 W desktop TGP.** Unlike the 55 W laptop 4070, this card sustains its
  clocks, so per-replica throughput here should beat the laptop's on long runs.
  Different GPU generations are fine: Kubernetes schedules by `nvidia.com/gpu`
  **count**, not model.
- **WDDM driver model** (not TCC), normal for consumer GPUs. The desktop
  compositor reserves a little VRAM. The GPU still passes through to WSL2 and to
  containers via the NVIDIA Container Toolkit.

---

## 3. Network state

| Setting | Value |
|---------|-------|
| Active interface | **Wired Ethernet** (Realtek Gaming 2.5GbE Family Controller) |
| Current IPv4 | `192.168.18.2` (Ethernet MAC `D8-BB-C1-CC-BE-D9`, link 2.5 Gbps; k3s API endpoint `:6443`) |
| Subnet / gateway | `192.168.18.0/24`, gateway `192.168.18.1` (same LAN as the laptop's `.142`) |
| Workgroup | `WORKGROUP` (not domain-joined) |
| Other NICs | Wi-Fi + a second Ethernet present but unused (self-assigned `169.254.x.x`) |
| **WSL2 networking** | **Mirrored**: WSL `hostname -I` returns `192.168.18.2`, the same address Windows uses. k3s advertises this LAN IP as its internal IP. |

**Wired, low-latency, and stable, ideal for the always-on server.** This PC already
sits on `192.168.18.2` over 2.5 GbE on the same switch/LAN as the laptop. The laptop
agent's join URL and the Mac's kubeconfig will both point here, so **pin this IP**:
add a DHCP reservation for MAC `D8-BB-C1-CC-BE-D9` in the router (`http://192.168.18.1`),
or set a static IP. A changed IP breaks the cluster.

**Mirrored networking is still required.** Today WSL2 sits behind NAT
(`172.28.35.147`), so the in-WSL k3s server isn't reachable from the laptop/Mac.
After enabling mirrored mode ([step 2](#4-setup-steps-this-machine)), `hostname -I`
inside WSL should return `192.168.18.2`, the same address Windows uses.

---

## 4. Setup steps (this machine)

State as of capture: **WSL2 + Ubuntu and GPU passthrough are already done**
(`nvidia-smi -L` works in WSL). What remains:

1. **NVIDIA Container Toolkit** (in WSL2 Ubuntu): the 3 commands in
   [`diy-cluster.md` → NVIDIA Container Toolkit](../phase-2-capstone/gpu-node/diy-cluster.md#both-windows-machines-pc-and-laptop).
   Do **not** install a Linux GPU driver inside WSL. The Windows driver provides CUDA.

2. **Mirrored networking.** Create `C:\Users\ajkai\.wslconfig`, then `wsl --shutdown`:

   ```ini
   [wsl2]
   networkingMode=mirrored
   firewall=true
   ```

   Verify after restart: `hostname -I` in WSL returns `192.168.18.2`.

3. **Install the k3s server** (in WSL2 Ubuntu):

   ```bash
   curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
   hostname -I                                        # LAN IP — give to the laptop + Mac
   sudo cat /var/lib/rancher/k3s/server/node-token    # node-token — give to the laptop
   ```

4. **Open the firewall** for the agent + kubelet, scoped to the LAN subnet. See the
   [ports table](../phase-2-capstone/gpu-node/diy-cluster.md#firewall-ports-between-machines):
   **6443/TCP** (API server), **8472/UDP** (flannel VXLAN), **10250/TCP** (kubelet).

5. **Advertise the GPU.** With the NVIDIA Container Toolkit installed (step 1), k3s
   auto-detects it on (re)start and creates a `nvidia` `RuntimeClass`. Do **not**
   run `nvidia-ctk runtime configure` (that breaks the CNI; see the callout in §1).
   Install the device plugin and pin it to that runtime class:

   ```bash
   k3s kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.16.2/deployments/static/nvidia-device-plugin.yml
   k3s kubectl -n kube-system patch daemonset nvidia-device-plugin-daemonset \
     --type merge -p '{"spec":{"template":{"spec":{"runtimeClassName":"nvidia"}}}}'
   k3s kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"  gpu="}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'
   # expect: kaiser-desktop  gpu=1
   ```

   The device-plugin DaemonSet is cluster-wide, so once the laptop joins it schedules
   there too, with no need to re-apply it on the laptop.

6. **Hand the Mac a kubeconfig:** copy `/etc/rancher/k3s/k3s.yaml` from this PC to the
   Mac, replace `127.0.0.1` with `192.168.18.2`, and save as `~/.kube/config`. The Mac
   authenticates with this kubeconfig, **not** the node-token. See
   [Credentials](../phase-2-capstone/gpu-node/diy-cluster.md#credentials-how-each-machine-authenticates).

---

## Appendix A — capturing specs

On Windows (PowerShell):

```powershell
Get-CimInstance Win32_ComputerSystem | Select Manufacturer,Model,TotalPhysicalMemory,Name,Workgroup
Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
Get-CimInstance Win32_OperatingSystem | Select Caption,Version,BuildNumber,OSArchitecture
nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap,power.limit,uuid --format=csv
Get-NetIPConfiguration | ? {$_.IPv4Address}
Get-NetAdapter | ? Status -eq 'Up' | Select Name,InterfaceDescription,LinkSpeed,MacAddress
```

Inside WSL2 Ubuntu:

```bash
nvidia-smi -L                 # GPU visible to Linux
nvidia-ctk --version          # container toolkit
hostname -I                   # should match the Windows LAN IP (mirrored mode)
sudo k3s kubectl get nodes    # once the server is up
```
