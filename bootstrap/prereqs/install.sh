#!/usr/bin/env bash
#
# GPU node prerequisites: the NVIDIA device plugin (advertises `nvidia.com/gpu` so
# vLLM can request it) and the GPU metrics exporter — the `ds nvidia-gpu-exporter`
# that netfix() patches to hostNetwork. Neither ships with k3s or kube-prometheus-
# stack, so without this layer that patch is a no-op against a DaemonSet that was
# never created and `make up` can't reach a scraped GPU deployment on its own.
#
# Assumes the NVIDIA Container Toolkit is already installed on every GPU node and
# k3s has auto-detected it (creating the `nvidia` RuntimeClass) — that part needs
# real hardware and can't be scripted from here. See
# ../../phase-2-capstone/gpu-node/diy-cluster.md for that step, including why
# `nvidia-ctk runtime configure` must NOT be run against k3s.
set -euo pipefail
KUBECTL="${KUBECTL:-kubectl}"; kctl() { $KUBECTL "$@"; }
DEVICE_PLUGIN_VER="${DEVICE_PLUGIN_VER:-v0.16.2}"
GPU_EXPORTER_VER="${GPU_EXPORTER_VER:-}"   # empty = chart's latest

up() {
  echo "==> NVIDIA device plugin $DEVICE_PLUGIN_VER (advertises nvidia.com/gpu)"
  kctl apply -f "https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/$DEVICE_PLUGIN_VER/deployments/static/nvidia-device-plugin.yml"
  # cluster-wide DaemonSet; pin it to the runtime k3s auto-created (see diy-cluster.md)
  kctl -n kube-system patch daemonset nvidia-device-plugin-daemonset \
    --type merge -p '{"spec":{"template":{"spec":{"runtimeClassName":"nvidia"}}}}'
  kctl -n kube-system rollout status ds/nvidia-device-plugin-daemonset --timeout=300s || true

  echo "==> nvidia-gpu-exporter (GPU util/mem/temp/power on :9835)"
  command -v helm >/dev/null || { echo "helm is required"; exit 1; }
  helm repo add nvidia-gpu-exporter https://utkuozdemir.github.io/nvidia_gpu_exporter >/dev/null 2>&1 || true
  helm repo update >/dev/null
  # runtimeClassName=nvidia gets driver access from the NVIDIA container runtime;
  # deliberately no nvidia.com/gpu request (that would take a whole GPU away from
  # vLLM — see the chart's own README). fullnameOverride pins the DaemonSet's name
  # to what netfix() expects to find and patch.
  helm upgrade -i nvidia-gpu-exporter nvidia-gpu-exporter/nvidia-gpu-exporter \
    ${GPU_EXPORTER_VER:+--version "$GPU_EXPORTER_VER"} \
    -n monitoring --create-namespace \
    --set runtimeClassName=nvidia \
    --set fullnameOverride=nvidia-gpu-exporter
  kctl -n monitoring rollout status ds/nvidia-gpu-exporter --timeout=300s || true
}

down() {
  helm uninstall nvidia-gpu-exporter -n monitoring 2>/dev/null || true
  kctl delete --ignore-not-found -f "https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/$DEVICE_PLUGIN_VER/deployments/static/nvidia-device-plugin.yml" || true
}

"${1:?up|down}"
