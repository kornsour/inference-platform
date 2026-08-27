# Prereqs: vendored cluster-level GPU artifacts

Manifests that must exist on the cluster before the rest of `../platform.sh`'s layers
come up — the device plugin advertises `nvidia.com/gpu` to the scheduler, and the
exporter feeds GPU telemetry to Prometheus (what `netfix`'s hostNetwork patch targets).
[`install.sh`](install.sh) applies them, wired into the `prereqs` layer / `make -C
bootstrap prereqs`; see `../README.md`'s layer table.

Vendored as committed YAML instead of `kubectl apply -f <upstream-url>` / a live `helm
install` (which is what this layer, and
[`phase-2-capstone/gpu-node/diy-cluster.md`](../../phase-2-capstone/gpu-node/diy-cluster.md),
used to do) so the exact manifests applied to this cluster are reviewable, diffable, and
pinned in git rather than resolved from a moving upstream tag/chart at apply time.

## Files

| File | What | Source |
|---|---|---|
| [`nvidia-device-plugin.yaml`](nvidia-device-plugin.yaml) | NVIDIA k8s-device-plugin DaemonSet — advertises `nvidia.com/gpu`, one whole GPU per replica | [NVIDIA/k8s-device-plugin `v0.16.2`](https://github.com/NVIDIA/k8s-device-plugin/tree/v0.16.2), vendored + `runtimeClassName: nvidia` baked in |
| [`nvidia-device-plugin-timeslicing.yaml`](nvidia-device-plugin-timeslicing.yaml) | Same DaemonSet **plus** a time-slicing `ConfigMap` — advertises 2 schedulable `nvidia.com/gpu` units per physical card | Same base, extended per the plugin's ["Shared Access to GPUs"](https://github.com/NVIDIA/k8s-device-plugin/blob/v0.16.2/README.md#shared-access-to-gpus) config |
| [`nvidia-gpu-exporter.yaml`](nvidia-gpu-exporter.yaml) | GPU telemetry (util/mem/temp/power) on `:9835/metrics`, `hostNetwork` | plain-manifest port of the [utkuozdemir/nvidia_gpu_exporter](https://github.com/utkuozdemir/nvidia_gpu_exporter/tree/v1.14.0) Helm chart's DaemonSet template, pinned to release `v1.14.0` (image tag `1.14.0`) |

## Apply

Via `install.sh` (what `../platform.sh prereqs` / `make -C bootstrap prereqs` runs):

```bash
KUBECTL="k3s kubectl" ./install.sh up      # plain device plugin (default) + exporter
GPU_TIME_SLICING=1 KUBECTL="k3s kubectl" ./install.sh up   # time-sliced variant instead
./install.sh down                          # tear both down
```

Or by hand — pick **one** of the two device-plugin manifests, they share a
name/namespace so applying one replaces the other:

```bash
# Plain: one nvidia.com/gpu per physical card (default; matches vllm-2gpu.yaml — one
# replica per GPU, see phase-2-capstone/gpu-node/vllm-2gpu.yaml)
kubectl apply -f nvidia-device-plugin.yaml

# OR time-sliced: 2 schedulable nvidia.com/gpu units per physical card, to demonstrate
# a shared card (see phase-2-capstone/gpu-node/vllm-timeslice.yaml)
kubectl apply -f nvidia-device-plugin-timeslicing.yaml

# Either way, then the exporter:
kubectl apply -f nvidia-gpu-exporter.yaml
```

Re-running the device plugin's DaemonSet pods restarts every pod currently using a GPU
(the plugin re-registers its resource pool), so switch variants between demo runs, not
mid-run.

## Why time-slicing, not MIG

MIG (Multi-Instance GPU) partitions a card into hardware-isolated slices, but it's an
Ampere-and-later **datacenter** feature (A100, H100, ...) — `nvidia-smi mig -lgip`
reports unsupported on GeForce/RTX, full stop, no driver version fixes it. Neither of
this cluster's cards (RTX 3060 Ti, RTX 4070 Laptop — see
[diy-cluster.md](../../phase-2-capstone/gpu-node/diy-cluster.md)) can do it. The
applicable mechanism on consumer GeForce hardware is CUDA **time-slicing**
(what's configured here — interleaved compute, no isolation between the sharing
workloads) or **MPS** (space-partitioned, needs a control daemon, mutually exclusive
with time-slicing). Time-slicing is also what makes `maxReplicaCount: 2` in
[`keda-scaledobject-gpu.yaml`](../../phase-2-capstone/gpu-node/keda-scaledobject-gpu.yaml)
worth revisiting past "one replica per card" — see
[`vllm-timeslice.yaml`](../../phase-2-capstone/gpu-node/vllm-timeslice.yaml).
