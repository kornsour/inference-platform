#!/usr/bin/env bash
#
# Envoy AI Gateway — token-aware routing + rate limiting in front of vLLM.
# The heaviest, most networking-sensitive layer on this cluster (Gateway data plane +
# Gateway API CRDs). Needs helm. Versions track the Envoy AI Gateway docs — bump as needed.
set -euo pipefail
KUBECTL="${KUBECTL:-kubectl}"; kctl() { $KUBECTL "$@"; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EG_VER="${EG_VER:-v1.2.4}"          # envoy gateway (base)
AIEG_VER="${AIEG_VER:-v0.1.5}"      # envoy ai gateway

up() {
  command -v helm >/dev/null || { echo "helm is required"; exit 1; }
  echo "==> Envoy Gateway $EG_VER"
  helm upgrade -i eg oci://docker.io/envoyproxy/gateway-helm --version "$EG_VER" \
    -n envoy-gateway-system --create-namespace
  kctl -n envoy-gateway-system rollout status deploy/envoy-gateway --timeout=300s || true
  echo "==> Envoy AI Gateway $AIEG_VER"
  helm upgrade -i aieg oci://docker.io/envoyproxy/ai-gateway-helm --version "$AIEG_VER" \
    -n envoy-ai-gateway-system --create-namespace
  kctl -n envoy-ai-gateway-system rollout status deploy --timeout=300s || true
  echo "==> route -> vLLM"
  kctl apply -f "$HERE/ai-gateway.yaml"
}

down() {
  kctl delete -f "$HERE/ai-gateway.yaml" --ignore-not-found || true
  helm uninstall aieg -n envoy-ai-gateway-system 2>/dev/null || true
  helm uninstall eg -n envoy-gateway-system 2>/dev/null || true
}

"${1:?up|down}"
