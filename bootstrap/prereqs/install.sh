#!/usr/bin/env bash
#
# GPU node prerequisites: the NVIDIA device plugin (advertises `nvidia.com/gpu` so
# vLLM can request it) and the GPU metrics exporter — the `ds nvidia-gpu-exporter`
# that netfix() patches to hostNetwork. Neither ships with k3s or kube-prometheus-
# stack, so without this layer that patch is a no-op against a DaemonSet that was
# never created and `make up` can't reach a scraped GPU deployment on its own.
#
# Both are applied from the manifests vendored alongside this script (see README.md)
# instead of `kubectl apply -f <upstream-url>` / a live `helm install` — the exact
# YAML this cluster runs is reviewable and pinned in git, not resolved from a moving
# upstream tag/chart at install time.
#
# Assumes the NVIDIA Container Toolkit is already installed on every GPU node and
# k3s has auto-detected it (creating the `nvidia` RuntimeClass) — that part needs
# real hardware and can't be scripted from here. See
# ../../phase-2-capstone/gpu-node/diy-cluster.md for that step, including why
# `nvidia-ctk runtime configure` must NOT be run against k3s.
set -euo pipefail
KUBECTL="${KUBECTL:-kubectl}"; kctl() { $KUBECTL "$@"; }
# 1 = advertise 2 schedulable nvidia.com/gpu units per physical card (CUDA
# time-slicing) instead of 1, to demo a shared card — see
# ../../phase-2-capstone/gpu-node/vllm-timeslice.yaml. The two device-plugin
# manifests are mutually exclusive (same DaemonSet name/namespace); default is the
# plain one, matching what vllm-2gpu.yaml (one replica per card) expects.
GPU_TIME_SLICING="${GPU_TIME_SLICING:-0}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEVICE_PLUGIN_MANIFEST="$DIR/nvidia-device-plugin.yaml"
[ "$GPU_TIME_SLICING" = "1" ] && DEVICE_PLUGIN_MANIFEST="$DIR/nvidia-device-plugin-timeslicing.yaml"

up() {
  echo "==> NVIDIA device plugin ($(basename "$DEVICE_PLUGIN_MANIFEST"))"
  kctl apply -f "$DEVICE_PLUGIN_MANIFEST"
  kctl -n kube-system rollout status ds/nvidia-device-plugin-daemonset --timeout=300s || true

  echo "==> nvidia-gpu-exporter (GPU util/mem/temp/power on :9835)"
  kctl apply -f "$DIR/nvidia-gpu-exporter.yaml"
  kctl -n monitoring rollout status ds/nvidia-gpu-exporter --timeout=300s || true
}

down() {
  kctl delete --ignore-not-found -f "$DIR/nvidia-gpu-exporter.yaml" || true
  # Delete both variants: whichever was actually applied, this removes the
  # DaemonSet + ConfigMap by name/namespace regardless of which file is passed.
  kctl delete --ignore-not-found -f "$DIR/nvidia-device-plugin-timeslicing.yaml" || true
  kctl delete --ignore-not-found -f "$DIR/nvidia-device-plugin.yaml" || true
}

"${1:?up|down}"
