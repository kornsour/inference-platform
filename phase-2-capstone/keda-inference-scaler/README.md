# keda-inference-scaler (Go)

A custom **KEDA external scaler** that autoscales an LLM serving Deployment on a
composite inference-saturation signal. It is the real code component of the capstone,
not just YAML.

> **Published standalone** (genericized, Apache-2.0) at
> [github.com/kornsour/keda-inference-scaler](https://github.com/kornsour/keda-inference-scaler)
> and listed in KEDA's community scalers ([external-scalers#34](https://github.com/kedacore/external-scalers/pull/34)).
> This in-repo copy is the capstone's working version.

## Why it exists

KEDA's built-in `prometheus` scaler reacts to **one** query. But inference saturation is
two-dimensional:

- a **request queue** forms when the GPU's *compute* is the bottleneck, and
- the **KV cache** fills when *memory* is the bottleneck.

A small model is compute-bound (queue grows, KV stays low); a larger one is KV-bound (KV
fills, queue grows only once KV is full), as the [real-GPU results](../gpu-node/real-gpu-results.md) show.
This scaler queries **both** and scales on whichever is closer to its threshold, exposing a
single normalized metric:

```
inference-saturation = max(queueDepth / queueThreshold, kvCacheUtil / kvThreshold) * 100
```

`100` means "exactly at threshold", and KEDA scales out when it exceeds that. One trigger
covers both failure modes, which a single PromQL trigger can't express.

## Build & test

```bash
make test     # go vet + unit tests (generates stubs first)
make build    # static binary in ./bin
make image    # container image (protoc + build inside Docker)
```

The gRPC stubs under `externalscaler/` are generated from `externalscaler.proto` (KEDA's
external-scaler contract) via `make proto`, or automatically in the Dockerfile and CI.

CI also runs [`check-sync.sh`](check-sync.sh), which diffs `main.go`, `main_test.go` and
`Dockerfile` against the standalone repo and fails the build if this copy has drifted. Port
any change to both repos (or run the script locally after a change here or there).

## Deploy

This is the **default** scaling path — `bootstrap/platform.sh`'s `autoscaling()` layer and
`gitops/applications.yaml`'s `inference-scaler` Application both deploy/sync it, in place of
the built-in-scaler `gpu-node/keda-scaledobject-gpu.yaml` alternative.

`deploy/scaler.yaml` runs the scaler (Deployment + Service on `:6000`).
`deploy/scaledobject-external.yaml` is a KEDA `ScaledObject` whose `external` trigger points
at it. Note `prometheusAddress` uses the **laptop node IP and NodePort**, not the Prometheus
ClusterIP, because cross-node ClusterIP routing is down on this WSL2 cluster. The scaler reaches
Prometheus over plain LAN TCP (see the [troubleshooting log](../../docs/cluster-troubleshooting-log.md)).

```bash
kubectl apply -f deploy/scaler.yaml
kubectl apply -f deploy/scaledobject-external.yaml
kubectl get scaledobject,hpa -n inference
```

## Configuration (ScaledObject `trigger.metadata`)

| key | default | meaning |
|---|---|---|
| `prometheusAddress` | _(required)_ | base URL of Prometheus, e.g. `http://192.168.18.142:9090` |
| `queueQuery` | `sum(vllm:num_requests_waiting)` | PromQL for queue depth |
| `kvCacheQuery` | `max(vllm:gpu_cache_usage_perc)` | PromQL for KV-cache utilization |
| `queueThreshold` | `3` | queue depth that counts as "at threshold" |
| `kvCacheThreshold` | `0.7` | KV-cache fraction that counts as "at threshold" |
| `activationThreshold` | `1` | saturation below which the target may scale to zero |
