# DIY two-GPU Kubernetes cluster (PC + laptop)

Two Windows machines with NVIDIA GPUs joined as worker nodes give you something
a single GPU can't: **real multi-replica GPU autoscaling** — KEDA scaling vLLM
pods across two physical GPUs on the queue/KV-cache signal. That completes the
capstone story end to end, for $0.

## Topology

```text
   Mac (this repo)            Windows PC                 Windows laptop
   kubectl + helm   ──API──▶  WSL2 Ubuntu                WSL2 Ubuntu
   GitOps / CI                k3s SERVER + GPU worker     k3s AGENT + GPU worker
                             (12 GB GPU)                 (gaming GPU)
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
# in WSL2 Ubuntu on the laptop
curl -sfL https://get.k3s.io | K3S_URL=https://<PC-LAN-IP>:6443 \
  K3S_TOKEN=<token-from-server> sh -
```

### Both nodes — advertise the GPU

Point k3s's bundled containerd at the NVIDIA runtime, then install the device
plugin so nodes advertise `nvidia.com/gpu`:

```bash
sudo nvidia-ctk runtime configure --runtime=containerd \
  --config=/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl
sudo systemctl restart k3s   # (k3s-agent on the laptop)
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.16.2/deployments/static/nvidia-device-plugin.yml
```

### Mac — point kubectl at the cluster

```bash
# copy /etc/rancher/k3s/k3s.yaml from the PC, then on the Mac:
#   - replace 127.0.0.1 with the PC's LAN IP
#   - save as ~/.kube/config (or KUBECONFIG=...)
kubectl get nodes -o wide        # should list PC (control-plane) + laptop
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'
# each node should report 1 GPU
```

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
   vLLM) with a 12 GB-friendly model — one replica lands on each GPU node.
3. Apply [`../k8s/keda-scaledobject.yaml`](../k8s/keda-scaledobject.yaml) and
   [`../k8s/podmonitor.yaml`](../k8s/podmonitor.yaml) — the **same** objects
   validated locally, now scaling **real vLLM across two GPUs**.
4. Re-run the load + capture from [`../loadtest/`](../loadtest/) and drop the real
   numbers into [`../WRITEUP.md`](../WRITEUP.md). This time scale-out is genuine
   GPU scale-out.

## Reality check

- **Different GPUs are fine** — Kubernetes schedules by `nvidia.com/gpu` count,
  not model. Size the model to the *smaller* of the two cards.
- **Laptop sleeping** → its node goes `NotReady` and pods reschedule; fine for
  demos, just keep it awake during a run.
- **If WSL2 networking fights you**, fall back to single-GPU
  [Option A](README.md). The mock already proves the scaling loop, so the DIY
  cluster is upside, not a dependency.
