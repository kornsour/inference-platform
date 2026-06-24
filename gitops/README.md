# GitOps (Argo CD)

Declarative continuous delivery for the inference platform: git is the source of truth,
Argo CD reconciles the cluster to match. This is the **CD** half of the platform's
GitOps/CI story — the **CI** half ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml))
lints, schema-validates, and builds every change before it merges.

## Applications

[`applications.yaml`](applications.yaml) defines two Argo CD `Application`s:

| Application | Syncs | Into |
|---|---|---|
| `inference-serving` | `vllm-2gpu.yaml` + `keda-scaledobject-gpu.yaml` | `inference` ns |
| `inference-scaler` | the Go external scaler `Deployment`/`Service` | `inference` ns |

Both use `automated` sync with `prune` + `selfHeal`, so drift is corrected and deletions in
git propagate. A directory `include` filter keeps the *alternative* manifests in
`gpu-node/` (`vllm-plain.yaml`, `kserve-inferenceservice.yaml`) out of the synced set —
they're documented options, not the running desired state.

## Install & apply

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -f gitops/applications.yaml
argocd app list      # or the Argo CD UI
```

!!! note "Same WSL2 caveat as KServe/KEDA"
    Argo CD ships admission/redis/repo-server components and (like cert-manager, KServe,
    and KEDA) is **webhook- and in-cluster-networking-sensitive**. On this broken-overlay
    cluster its controllers should be **co-located with the API server** (cordon the laptop
    during install), for the reasons in the
    [troubleshooting log](../docs/cluster-troubleshooting-log.md) and
    [architecture decisions](../phase-2-capstone/architecture-decisions.md). On a healthy
    CNI none of that is needed.

## Status

The `Application` definitions are committed and CI-validated. Installing Argo CD on the DIY
cluster is the remaining step to make delivery fully hands-off; until then deploys are
`kubectl apply` of the same manifests Argo would sync.
