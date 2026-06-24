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
| `platform` | cert-manager → KEDA → KServe | controllers + webhooks; the **agent is cordoned** first so they land on the API-server node |
| `netfix` | hostNetwork Prometheus + GPU exporters; CoreDNS → server | the overlay workarounds that make metrics + DNS reachable |
| `serving` | vLLM (two-GPU) + nginx LB | the workload |
| `autoscaling` | KEDA `ScaledObject` (queue + KV-cache) | needs Prometheus reachable (netfix) |
| `gitops` | Argo CD + `Application`s | declarative CD for the above |
| `gateway` | Envoy AI Gateway | token-aware front door |

`down` runs the reverse, and finally **uncordons** the agent.

## Prerequisites

- A running **k3s** cluster (server + GPU agent) with the NVIDIA device plugin (see the
  [cluster runbook](../phase-2-capstone/gpu-node/diy-cluster.md)).
- **kube-prometheus-stack** installed in `monitoring` (the `netfix` layer patches it).
- **helm** on PATH for the `gateway` layer.
- `kubectl` pointed at the cluster (`KUBECTL="k3s kubectl"` on the server).

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
```
