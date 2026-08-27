#!/usr/bin/env bash
#
# platform.sh — one-command bootstrap / teardown for the DIY inference platform.
#
# Encodes the full, ordered install (and reverse teardown) of every layer, INCLUDING
# the WSL2-mirrored-mode workarounds discovered the hard way (see
# docs/cluster-troubleshooting-log.md and phase-2-capstone/architecture-decisions.md):
#   * cordon the agent during installs so webhook-backed controllers co-locate with the
#     API server (cross-node ClusterIP / webhooks are unreachable over the broken overlay);
#   * patch Prometheus + the GPU exporters to hostNetwork so they're reachable by node IP;
#   * reschedule CoreDNS onto the server so pods can resolve names.
#
# Usage:
#   ./platform.sh up                 # bring up the whole stack
#   ./platform.sh down               # tear it all down (reverse order)
#   ./platform.sh status             # what's running
#   ./platform.sh <layer>            # run a single layer: platform|netfix|serving|
#                                    #   autoscaling|gitops|gateway
#   ./platform.sh down-<layer>       # tear down a single layer
#
# Runs wherever kubectl targets the cluster. On the k3s server, export:
#   KUBECTL="k3s kubectl"
set -euo pipefail

# ---- cluster config (override via environment) ----
KUBECTL="${KUBECTL:-kubectl}"
AGENT_NODE="${AGENT_NODE:-kaiser-laptop}"
AGENT_IP="${AGENT_IP:-192.168.18.142}"
PROM_ADDR="${PROM_ADDR:-http://192.168.18.142:9090}"
CERT_MANAGER_VER="${CERT_MANAGER_VER:-v1.16.2}"
KSERVE_VER="${KSERVE_VER:-v0.14.1}"
KEDA_VER="${KEDA_VER:-v2.16.1}"

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
GPU="$REPO_ROOT/phase-2-capstone/gpu-node"
ENVOY_DIR="$(dirname "${BASH_SOURCE[0]}")/envoy"

kctl() { $KUBECTL "$@"; }
log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
wait_avail() { kctl wait --for=condition=Available deploy --all -n "$1" --timeout=300s || true; }
cordon()   { log "cordon $AGENT_NODE (webhooks must reach the API server)"; kctl cordon "$AGENT_NODE" || true; }
uncordon() { log "uncordon $AGENT_NODE"; kctl uncordon "$AGENT_NODE" || true; }

# ---------------------------------------------------------------------------- layers

platform() { # cert-manager + KEDA + KServe (all webhook-backed -> cordon first)
  cordon
  log "cert-manager $CERT_MANAGER_VER"
  kctl apply -f "https://github.com/cert-manager/cert-manager/releases/download/$CERT_MANAGER_VER/cert-manager.yaml"
  kctl delete pods -n cert-manager --all --wait=false || true   # reschedule onto the server
  wait_avail cert-manager
  log "KEDA $KEDA_VER"
  kctl apply --server-side -f "https://github.com/kedacore/keda/releases/download/$KEDA_VER/keda-$KEDA_VER.yaml"
  wait_avail keda
  log "KServe $KSERVE_VER (controller first, then cluster resources)"
  kctl apply --server-side -f "https://github.com/kserve/kserve/releases/download/$KSERVE_VER/kserve.yaml"
  kctl wait --for=condition=Available deploy/kserve-controller-manager -n kserve --timeout=300s || true
  kctl apply --server-side -f "https://github.com/kserve/kserve/releases/download/$KSERVE_VER/kserve-cluster-resources.yaml"
}

netfix() { # WSL2 overlay workarounds (idempotent patches)
  log "overlay workarounds: hostNetwork Prometheus + GPU exporters, CoreDNS -> server"
  kctl patch prometheus kube-prometheus-stack-prometheus -n monitoring --type merge \
    -p '{"spec":{"hostNetwork":true}}' || true
  kctl -n monitoring patch ds nvidia-gpu-exporter --type merge \
    -p '{"spec":{"template":{"spec":{"hostNetwork":true,"dnsPolicy":"ClusterFirstWithHostNet"}}}}' || true
  kctl delete pod -n kube-system -l k8s-app=kube-dns --wait=false || true
}

serving()     { log "vLLM two-GPU serving + LB";  kctl apply -f "$GPU/vllm-2gpu.yaml"
                log "SLO/error-budget/cost PrometheusRule"; kctl apply -f "$GPU/slo-prometheusrule.yaml"; }
autoscaling() { log "KEDA ScaledObject (queue + KV-cache)"; kctl apply -f "$GPU/keda-scaledobject-gpu.yaml"; }

gitops() {
  log "Argo CD"
  kctl create namespace argocd --dry-run=client -o yaml | kctl apply -f -
  kctl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
  wait_avail argocd
  kctl apply -f "$REPO_ROOT/gitops/applications.yaml"
}

gateway() { log "Envoy AI Gateway"; "$ENVOY_DIR/install.sh" up; }

# ---------------------------------------------------------------------------- teardown

down-gateway()     { "$ENVOY_DIR/install.sh" down || true; }
down-gitops()      { kctl delete -f "$REPO_ROOT/gitops/applications.yaml" --ignore-not-found || true
                     kctl delete -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml --ignore-not-found || true
                     kctl delete namespace argocd --ignore-not-found || true; }
down-autoscaling() { kctl delete -f "$GPU/keda-scaledobject-gpu.yaml" --ignore-not-found || true; }
down-serving()     { kctl delete -f "$GPU/slo-prometheusrule.yaml" --ignore-not-found || true
                     kctl delete -f "$GPU/vllm-2gpu.yaml" --ignore-not-found || true; }
down-platform()    {
  kctl delete --ignore-not-found -f "https://github.com/kserve/kserve/releases/download/$KSERVE_VER/kserve.yaml" || true
  kctl delete --ignore-not-found -f "https://github.com/kedacore/keda/releases/download/$KEDA_VER/keda-$KEDA_VER.yaml" || true
  kctl delete --ignore-not-found -f "https://github.com/cert-manager/cert-manager/releases/download/$CERT_MANAGER_VER/cert-manager.yaml" || true
}

# ---------------------------------------------------------------------------- compose

up()   { platform; netfix; serving; autoscaling; gitops; gateway; uncordon; log "UP complete"; status; }
down() { down-gateway; down-gitops; down-autoscaling; down-serving; down-platform; uncordon; log "DOWN complete"; }

status() {
  log "nodes";        kctl get nodes
  log "inference";    kctl get pods,svc -n inference -o wide 2>/dev/null || true
  log "autoscaling";  kctl get scaledobject,hpa -n inference 2>/dev/null || true
  log "argo apps";    kctl get application -n argocd 2>/dev/null || true
  log "gateway";      kctl get gateway,aigatewayroute -A 2>/dev/null || true
}

"${1:?usage: platform.sh up|down|status|<layer>|down-<layer>}"
