# GPU Cluster Node — Windows PC (k3s server)

The **always-on Windows PC** is the **k3s _server_** *and* a GPU worker in the DIY
two-GPU cluster. Because the control plane must stay reachable, the API lives here;
the [laptop](cluster-node-kaiser-laptop.md) joins as an agent, and the MacBook Pro
is the **client** (`kubectl` / `helm`, GitOps/CI).

- **Cluster runbook (all machines, full steps):** [`diy-cluster.md`](../phase-2-capstone/gpu-node/diy-cluster.md)
- **Companion node:** [KAISER-LAPTOP — k3s agent](cluster-node-kaiser-laptop.md)

```text
   Mac (client)              THIS — Windows PC (server)   Windows laptop (agent)
   kubectl + helm   ──API──▶  WSL2 Ubuntu                 WSL2 Ubuntu
   GitOps / CI                k3s SERVER + GPU worker      k3s AGENT + GPU worker
```

> **k3s server is live (2026-06-23)** at `192.168.18.2`; the laptop agent has joined
> and both nodes advertise a GPU. **Hardware specs captured 2026-06-24** (§2) —
> RTX 3060 Ti, 8 GB, so both cluster GPUs are 8 GB.

---

## 1. Setup status

| Step | State |
|------|-------|
| WSL2 + Ubuntu installed | :material-check: |
| Windows NVIDIA driver + WSL GPU passthrough (`nvidia-smi` in WSL) | :material-check: |
| NVIDIA Container Toolkit (in WSL) | :material-check: |
| Mirrored networking (`.wslconfig`) | :material-check: |
| **k3s server installed** | :material-check: running at `192.168.18.2:6443` |
| Firewall: 6443/TCP, 8472/UDP, 10250/TCP open on the LAN | :material-check: agent joined; flannel VXLAN established |
| NVIDIA device plugin (advertise `nvidia.com/gpu`) | :material-check: applied cluster-wide; Running on both nodes |
| LAN IP + node-token handed to the laptop & Mac | :material-check: laptop joined · :material-timer-sand: Mac kubeconfig pending |

---

## 2. Hardware & OS specs

_Captured 2026-06-24. Re-run [Appendix A](#appendix-a--capturing-specs) after hardware/driver/OS changes._

| Component | Detail |
|-----------|--------|
| Make / model | Custom desktop build — MSI `MS-7C91` (B550 board) |
| Hostname | `KAISER-DESKTOP` |
| OS | Windows 11 Pro, version 10.0.26200 (build 26200), 64-bit |
| CPU | AMD Ryzen 5 5600X — 6 cores / 12 threads |
| RAM | 32 GB (31.9 GiB usable) |
| **Discrete GPU** | **NVIDIA GeForce RTX 3060 Ti** |
| VRAM | **8 GB GDDR6** (8192 MiB reported by `nvidia-smi`) |
| Driver version | 591.86 (Windows; provides the WSL CUDA stack) |
| NVIDIA Container Toolkit | v1.19.1 (in WSL) |

> **Cluster sizing:** both GPUs are **8 GB** (this card is an RTX 3060 Ti; the laptop
> is an RTX 4070 Laptop). The earlier plan assumed a 12 GB card here — it's 8 GB — so
> the two nodes are evenly matched and the deployed model targets **8 GB** on both.

---

## 3. Network

| Setting | Value |
|---------|-------|
| LAN IP | `192.168.18.2` (k3s server / API endpoint `:6443`) |
| Subnet / gateway | `192.168.18.0/24`, gateway `192.168.18.1` (same LAN as the laptop) |
| WSL2 networking | Mirrored (set in `.wslconfig`) — WSL shares the host LAN IP |

**Give the PC a stable IP.** The laptop agent's join URL and the Mac's kubeconfig
both point at this machine, so a changed IP breaks the cluster. Use a DHCP
reservation in the router (`http://192.168.18.1`) or a static IP. Wired Ethernet is
preferred for the always-on server.

---

## 4. Setup steps (this machine)

**Steps 1–4 are identical to the laptop.** Full commands:
[`diy-cluster.md` → Both Windows machines](../phase-2-capstone/gpu-node/diy-cluster.md#both-windows-machines-pc-and-laptop).

1. `wsl --install -d Ubuntu` (Admin PowerShell; reboot; create the Ubuntu user) +
   `wsl --update`.
2. In WSL: `nvidia-smi` lists the GPU. The **Windows** NVIDIA driver provides WSL
   CUDA — do **not** install a Linux GPU driver inside WSL.
3. In WSL: install the **NVIDIA Container Toolkit** (the doc's 3 commands).
4. Create `C:\Users\<you>\.wslconfig`, then `wsl --shutdown`:

   ```ini
   [wsl2]
   networkingMode=mirrored
   firewall=true
   ```

**PC-only — install the k3s server** (in WSL2 Ubuntu):

```bash
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
hostname -I                                        # LAN IP — give to the laptop + Mac
sudo cat /var/lib/rancher/k3s/server/node-token    # node-token — give to the laptop
```

**Open the firewall** for the agent + kubelet, scoped to the LAN subnet — see the
[ports table](../phase-2-capstone/gpu-node/diy-cluster.md#firewall-ports-between-machines):
**6443/TCP** (API server), **8472/UDP** (flannel VXLAN), **10250/TCP** (kubelet).

**Advertise the GPU** — on k3s `v1.35` the NVIDIA runtime is **auto-detected** (no
manual `nvidia-ctk` step needed). Apply the device plugin **once** from here and it
covers every GPU node in the cluster, the laptop included:

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.16.2/deployments/static/nvidia-device-plugin.yml
```

See [`diy-cluster.md` → Both nodes](../phase-2-capstone/gpu-node/diy-cluster.md#both-nodes--advertise-the-gpu).

**Hand the Mac a kubeconfig:** copy `/etc/rancher/k3s/k3s.yaml` from this PC to the
Mac, replace `127.0.0.1` with `192.168.18.2`, and save as `~/.kube/config`. The Mac
authenticates with this kubeconfig, **not** the node-token — see
[Credentials](../phase-2-capstone/gpu-node/diy-cluster.md#credentials--how-each-machine-authenticates).

---

## Appendix A — capturing specs

On Windows (PowerShell):

```powershell
Get-CimInstance Win32_ComputerSystem | Select Manufacturer,Model,TotalPhysicalMemory,Name,Workgroup
Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
Get-CimInstance Win32_OperatingSystem | Select Caption,Version,BuildNumber,OSArchitecture
nvidia-smi
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
