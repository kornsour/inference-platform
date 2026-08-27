# Bootstrap: spin up and tear down the platform for a demo

One command reconstitutes the whole inference platform on the DIY cluster, and one tears it
down. This is the "get it back up to demo" automation: the install **order** and every
WSL2-specific workaround are encoded so you don't have to remember them.

```bash
# on the k3s server (or anywhere kubectl targets the cluster)
export KUBECTL="k3s kubectl"        # k3s server; omit if plain kubectl is configured
make up        # bring up everything
make status    # see what's running
make down      # tear it all down
```

Per-layer targets let you bring up / tear down one piece: `make serving`, `make autoscaling`,
`make gitops`, `make gateway`, `make down-gateway`, … (see `make` / [`platform.sh`](platform.sh)).

## Layers (install order)

| Layer | What | Why the order |
|---|---|---|
| `prereqs` | NVIDIA device plugin + `nvidia-gpu-exporter` DaemonSet | must exist before `netfix` has anything to patch or `serving` has a GPU to request |
| `platform` | cert-manager → KEDA → KServe | controllers + webhooks; the **agent is cordoned** first so they land on the API-server node |
| `netfix` | hostNetwork Prometheus + GPU exporters; CoreDNS → server | the overlay workarounds that make metrics + DNS reachable |
| `serving` | vLLM (two-GPU) + nginx LB + `Service`/`PodMonitor`/SLO `PrometheusRule`/Grafana dashboard | the workload and everything that scrapes, alerts on, and dashboards it |
| `autoscaling` | custom Go external scaler + its `ScaledObject` (composite queue + KV-cache trigger) | needs Prometheus reachable (netfix) and the PodMonitor scraping (serving) |
| `gitops` | Argo CD + `Application`s | declarative CD for the above |
| `gateway` | Envoy AI Gateway | needs `Service/vllm-qwen` (serving) to route to |

`down` runs the reverse, and finally **uncordons** the agent.

## Prerequisites

What genuinely can't be scripted from here — needs real hardware or a one-time
manual step — versus what the `prereqs` layer now vendors for you:

- A running **k3s** cluster (server + GPU agent) with the **NVIDIA Container
  Toolkit** installed on each GPU node *before* k3s starts, so k3s auto-detects it
  and creates the `nvidia` `RuntimeClass` (see the
  [cluster runbook](../phase-2-capstone/gpu-node/diy-cluster.md) — this is also where
  the "do not run `nvidia-ctk runtime configure` against k3s" warning lives).
- **kube-prometheus-stack** installed in `monitoring` (the `netfix` layer patches it;
  see [`local/Makefile`](../phase-2-capstone/local/Makefile)'s `monitoring` target for
  the Helm install this repo uses elsewhere).
- **helm** on PATH for the `gateway` layer.
- `kubectl` pointed at the cluster (`KUBECTL="k3s kubectl"` on the server).

The `prereqs` layer itself installs the **NVIDIA device plugin** (advertises
`nvidia.com/gpu`) and the **`nvidia-gpu-exporter`** DaemonSet (GPU util/mem/temp/power
on `:9835`, the `netfix` layer's hostNetwork patch target) from manifests vendored in
[`prereqs/`](prereqs/README.md) — committed, pinned copies instead of `kubectl apply -f
<upstream-url>` / a live `helm install` — via [`prereqs/install.sh`](prereqs/install.sh)
(see [`prereqs/README.md`](prereqs/README.md) for what's vendored and why). Neither
ships with k3s or kube-prometheus-stack, so before this layer existed `make up` on a
fresh cluster left `netfix`'s exporter patch as a no-op against a DaemonSet nothing had
created. Set `GPU_TIME_SLICING=1` to install the time-slicing device-plugin variant
instead of the plain one, advertising 2 schedulable `nvidia.com/gpu` units per card —
see
[`phase-2-capstone/gpu-node/vllm-timeslice.yaml`](../phase-2-capstone/gpu-node/vllm-timeslice.yaml).

## Why these workarounds exist

Every cordon / hostNetwork / reschedule step is a consequence of one root cause: **WSL2
mirrored networking doesn't carry flannel's cross-node overlay** (full story in the
[troubleshooting log](../docs/cluster-troubleshooting-log.md); the design implications in
[architecture decisions](../phase-2-capstone/architecture-decisions.md)). On a healthy CNI
this script collapses to plain `kubectl apply`s with no cordon dance. That is exactly the
gap between a homelab and production.

## Config

Override any of these via environment (defaults shown):

```
KUBECTL=kubectl  AGENT_NODE=kaiser-laptop  AGENT_IP=192.168.18.142
PROM_ADDR=http://192.168.18.142:9090
CERT_MANAGER_VER=v1.16.2  KSERVE_VER=v0.14.1  KEDA_VER=v2.16.1
GPU_TIME_SLICING=0   # 1 = time-sliced device plugin (2 GPU units/card); prereqs layer
```
