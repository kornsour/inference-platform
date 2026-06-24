# DIY two-GPU Kubernetes cluster (PC + laptop)

Two Windows machines with NVIDIA GPUs joined as worker nodes give you something
a single GPU can't: **real multi-replica GPU autoscaling** — KEDA scaling vLLM
pods across two physical GPUs on the queue/KV-cache signal. That completes the
capstone story end to end, for $0.

## Machines & roles

| Machine | Role | GPU | k3s | Setup status (2026-06-23) |
|---------|------|-----|-----|---------------------------|
| **Windows PC** (`KAISER-DESKTOP`, `192.168.18.2`) | k3s **server** + GPU worker; always-on, hosts the API | RTX 3060 Ti, **8 GB** | server | :material-check: **live** — server up, device plugin applied — [node doc](../../docs/cluster-node-windows-pc.md) |
| **Windows laptop** (`KAISER-LAPTOP`, `192.168.18.142`) | k3s **agent** + GPU worker | RTX 4070 Laptop, **8 GB** | agent | :material-check: **joined**, advertising `nvidia.com/gpu` — [node doc](../../docs/cluster-node-kaiser-laptop.md) |
| **MacBook Pro** | client only — `kubectl` / `helm`, GitOps/CI | — | — | :material-timer-sand: kubeconfig pending |

> **Model sizing:** both cards are **8 GB** (PC RTX 3060 Ti, laptop RTX 4070 Laptop),
> so the nodes are evenly matched — target **8 GB** for the model on both.

Per-machine hardware/network/state lives in the node docs:
[Windows PC](../../docs/cluster-node-windows-pc.md) ·
[KAISER-LAPTOP](../../docs/cluster-node-kaiser-laptop.md).

## Topology

```text
   Mac (this repo)            Windows PC                 Windows laptop
   kubectl + helm   ──API──▶  WSL2 Ubuntu                WSL2 Ubuntu
   GitOps / CI                k3s SERVER + GPU worker     k3s AGENT + GPU worker
                             (always-on, hosts API)      (RTX 4070 Laptop, 8 GB)
                                   ▲                            │
                                   └──────── LAN (k3s) ─────────┘
```

- **PC** = k3s **server** *and* a GPU worker (control plane needs no GPU, but the
  node can serve too). It's the always-on box, so it hosts the API.
- **Laptop** = k3s **agent** + GPU worker.
- **Mac** = client only: `kubectl`/`helm` with kubeconfig pointed at the PC.

> All Kubernetes nodes are **Linux** (WSL2 Ubuntu). The NVIDIA GPUs are reached
> through WSL2's GPU passthrough — you never run k8s on Windows directly.

## The one hard part: WSL2 networking

By default WSL2 sits behind NAT, so its Linux IP isn't reachable from the LAN —
which breaks multi-host clustering. The fix on **Windows 11 (22H2+)** is
**mirrored networking mode**, which puts WSL2 on the LAN with the host. Put this
in `C:\Users\<you>\.wslconfig` on **both** machines, then `wsl --shutdown`:

```ini
[wsl2]
networkingMode=mirrored
firewall=true
```

If you're on Windows 10 (no mirrored mode), this gets much harder (netsh
portproxy + flannel quirks) — at that point prefer the single-GPU
[Option A](README.md#option-a--vllm-in-wsl2-cluster-points-at-it) instead.

## Per-machine setup

### Both Windows machines (PC and laptop)

1. **Enable WSL2 + Ubuntu**

   ```powershell
   wsl --install -d Ubuntu        # then set up the Ubuntu user
   wsl --update
   ```

2. **NVIDIA driver for WSL** — install the latest **Game Ready / Studio driver on
   Windows** (it includes WSL CUDA support). Do **not** install a Linux GPU
   driver inside WSL. Verify inside Ubuntu:

   ```bash
   nvidia-smi          # must list your GPU
   ```

3. **NVIDIA Container Toolkit** (lets containers use the GPU):

   ```bash
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   ```

4. **Mirrored networking** (see above), then `wsl --shutdown` from PowerShell.
5. **Firewall** — allow the k3s ports between the two machines (see table below).

### PC — k3s server

```bash
# in WSL2 Ubuntu on the PC
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
sudo cat /var/lib/rancher/k3s/server/node-token      # copy this token
hostname -I                                           # note the PC's LAN IP
```

### Laptop — k3s agent

```bash
# in WSL2 Ubuntu on the laptop  (server is up at 192.168.18.2)
curl -sfL https://get.k3s.io | K3S_URL=https://192.168.18.2:6443 \
  K3S_TOKEN=<token-from-server> sh -     # token: sudo cat /var/lib/rancher/k3s/server/node-token on the PC
```

### Advertise the GPU (device plugin)

> **Do not run `nvidia-ctk runtime configure` against k3s.** Pointing it at
> `/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl` overwrites k3s's
> containerd template with a minimal one that drops the flannel CNI settings — the
> node goes `NotReady` with `cni plugin not initialized`. (Verified the hard way on
> 2026-06-23.) k3s **auto-detects** the NVIDIA Container Toolkit at startup and
> creates a `nvidia` `RuntimeClass` by itself — no template editing needed.

Because the toolkit was installed *before* k3s started, the `nvidia` runtime is
already present (`kubectl get runtimeclass` should list `nvidia`). Install the device
plugin **once from the server** and pin it to that runtime class; the DaemonSet is
cluster-wide, so it covers every node that joins (no per-node re-apply):

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.16.2/deployments/static/nvidia-device-plugin.yml
kubectl -n kube-system patch daemonset nvidia-device-plugin-daemonset \
  --type merge -p '{"spec":{"template":{"spec":{"runtimeClassName":"nvidia"}}}}'
```

> If a node installs the toolkit *after* k3s is already running, restart k3s there so
> it re-detects the runtime: `sudo systemctl restart k3s` (server) or
> `sudo systemctl restart k3s-agent` (agent).

### Mac — point kubectl at the cluster

```bash
# copy /etc/rancher/k3s/k3s.yaml from the PC, then on the Mac:
scp <pc-user>@192.168.18.2:/etc/rancher/k3s/k3s.yaml ~/.kube/config
sed -i '' 's#127.0.0.1#192.168.18.2#' ~/.kube/config     # macOS sed; point at the PC
kubectl get nodes -o wide        # should list PC (control-plane) + laptop
kubectl get nodes -o custom-columns=NODE:.metadata.name,GPU:'.status.allocatable.nvidia\.com/gpu'
# each GPU node should report 1
```

The Mac uses this kubeconfig, **not** a node-token (see
[Credentials](#credentials--how-each-machine-authenticates)). If `kubectl` fails TLS
because the IP isn't in the cert, reinstall the server with `--tls-san 192.168.18.2`.

## Credentials — how each machine authenticates

Two different secrets, easy to confuse:

| Machine | How it authenticates | Secret it holds |
|---------|---------------------|-----------------|
| **PC** (server) | it *is* the control plane | issues everything below |
| **Laptop** (agent) | kubelet joins the node pool with the server's **node-token** | the single `K10…` server node-token |
| **Mac** (client) | `kubectl` / `helm` hit the API with an **admin kubeconfig** | `k3s.yaml` (TLS client cert + key + CA) |

- The **node-token is not per-node** — there is **one** server token that *every*
  agent uses to join. It grants no `kubectl` access.
- The **Mac never joins the cluster** and needs **no token**. It needs the admin
  kubeconfig (`/etc/rancher/k3s/k3s.yaml` from the PC), with `127.0.0.1` swapped for
  the PC's LAN IP.
- If `kubectl` from the Mac fails TLS with an IP/SAN error, reinstall the server with
  `--tls-san <PC-LAN-IP>` (or add it and restart `k3s`) so the API cert covers that
  address.

## Firewall ports (between machines)

| Port | Proto | Purpose |
| ---: | --- | --- |
| 6443 | TCP | k3s API server (agent → server) |
| 8472 | UDP | flannel VXLAN (pod network) |
| 10250 | TCP | kubelet metrics (server ↔ agent) |

## Deploy across both GPUs

Once both nodes show `nvidia.com/gpu: 1`, you have a real GPU cluster. Then:

1. Install **KEDA** and **kube-prometheus-stack** (Helm, same as the local stack).
2. Apply [`../k8s/inferenceservice.yaml`](../k8s/inferenceservice.yaml) (KServe +
   vLLM) with an **8 GB-friendly** model (size to the smaller card — the laptop's
   8 GB) — one replica lands on each GPU node.
3. Apply [`../k8s/keda-scaledobject.yaml`](../k8s/keda-scaledobject.yaml) and
   [`../k8s/podmonitor.yaml`](../k8s/podmonitor.yaml) — the **same** objects
   validated locally, now scaling **real vLLM across two GPUs**.
4. Re-run the load + capture from [`../loadtest/`](../loadtest/) and drop the real
   numbers into [`../WRITEUP.md`](../WRITEUP.md). This time scale-out is genuine
   GPU scale-out.

## Running metrics from the Mac

With `~/.kube/config` pointed at the PC, the Mac drives all observability through
`kubectl` / `helm` — no SSH into the nodes. Three tiers, cheapest first.

### 1. Cluster + GPU inventory (works now)

```bash
kubectl get nodes -o wide
# GPUs each node advertises:
kubectl get nodes -o custom-columns=NODE:.metadata.name,GPU:'.status.allocatable.nvidia\.com/gpu'
# live node / pod resource usage (k3s bundles metrics-server):
kubectl top nodes
kubectl top pods -A
```

### 2. Ad-hoc GPU snapshot — `nvidia-smi` in a pod

Schedules a throwaway pod onto a GPU node and runs `nvidia-smi`. Save as
`gpu-smi.yaml`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-smi
spec:
  runtimeClassName: nvidia          # k3s auto-creates this; verify: kubectl get runtimeclass
  restartPolicy: Never
  # nodeName: kaiser-laptop         # uncomment to pin to a specific GPU node
  containers:
    - name: smi
      image: nvidia/cuda:12.4.1-base-ubuntu22.04
      args: ["nvidia-smi"]
      resources:
        limits:
          nvidia.com/gpu: 1
```

```bash
kubectl apply -f gpu-smi.yaml && kubectl logs -f gpu-smi
kubectl delete pod gpu-smi
```

### 3. Continuous GPU telemetry → Prometheus + Grafana (real dashboards)

The device plugin only advertises GPU *count* — not utilization, memory, temp, or
power. For those, run an exporter on the GPU nodes and scrape it with the capstone's
**kube-prometheus-stack**.

```bash
helm repo add gpu-helm-charts https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo update
helm install dcgm-exporter gpu-helm-charts/dcgm-exporter \
  -n monitoring --create-namespace --set serviceMonitor.enabled=true
# then port-forward Grafana to the Mac and import dashboard 12239 (NVIDIA DCGM):
kubectl -n monitoring port-forward svc/<grafana-svc> 3000:80   # http://localhost:3000
```

> **WSL2 + GeForce caveat:** DCGM has limited support on consumer GeForce cards under
> WSL2 — some `DCGM_FI_*` fields may come back empty. If so, use
> [`nvidia_gpu_exporter`](https://github.com/utkuozdemir/nvidia_gpu_exporter) instead;
> it just parses `nvidia-smi` (which works fine in WSL) and exposes util / mem / temp /
> power on `:9835/metrics`. Scrape it with a `PodMonitor` the same way.

These GPU signals sit alongside the inference metrics (TTFT, KV-cache %, queue depth)
the capstone already scrapes from vLLM — together they're what the autoscaling and the
write-up are built on.

## Reality check

- **Different GPUs are fine** — Kubernetes schedules by `nvidia.com/gpu` count,
  not model. Size the model to the *smaller* of the two cards (**8 GB** here — the
  laptop).
- **Laptop sleeping** → its node goes `NotReady` and pods reschedule; fine for
  demos, just keep it awake during a run.
- **If WSL2 networking fights you**, fall back to single-GPU
  [Option A](README.md). The mock already proves the scaling loop, so the DIY
  cluster is upside, not a dependency.
