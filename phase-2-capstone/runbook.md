# Runbook — LLM Inference Platform

> Operational guide for the autoscaling inference platform. Draft — local
> control plane; URLs/links fill in per environment.

## Service overview

- **What it serves:** an open-weights LLM behind an OpenAI-compatible endpoint
  (`/v1/chat/completions`). Locally this is the mock vLLM; on GPU it is KServe +
  vLLM.
- **Topology:** Service (ClusterIP, load-balances) → vLLM pods → `/metrics`.
  Prometheus scrapes; KEDA scales; Grafana + Alertmanager observe.
- **Namespaces:** `inference` (workload), `monitoring` (kube-prometheus-stack),
  `keda` (autoscaler).
- **Owner / on-call:** _you_.

## SLOs

| SLI | Objective | Where to see it |
| --- | --- | --- |
| TTFT p95 | < 1 s over rolling 5m | Grafana "LLM Inference Platform" → TTFT panel |
| Availability | 99.9% | `job:vllm_availability_ratio:5m` — Prometheus, or derive from the error-budget panel |
| Error rate | < 1% | `job:vllm_error_ratio:5m` — Prometheus, or derive from the error-budget panel |

SLIs are recording rules in [`local/manifests/slo-prometheusrule.yaml`](local/manifests/slo-prometheusrule.yaml)
(and its GPU-cluster twin, [`gpu-node/slo-prometheusrule.yaml`](gpu-node/slo-prometheusrule.yaml)).
Availability/error rate are computed from `vllm:request_success_total{finished_reason}`
— `finished_reason="stop"` counts as available, anything else (e.g. `"abort"`)
counts against the error budget. The mock's `ERROR_RATE` env var injects
synthetic aborts to exercise both SLIs and their alerts without touching TTFT.

Error budget: the TTFT SLO's 5% budget is also tracked as a **burn rate**
(`job:vllm_ttft_burn_rate:*`, at 5m/30m/1h/6h) — how many times faster than
sustainable the 30-day budget is being consumed. Cost is tracked the same way:
`job:inference_cost_per_1m_tokens:5m` derives $/1M tokens from GPU power draw
(`nvidia_smi_power_draw_watts`) × $/kWh ÷ throughput — see the recording rule's
comments in `slo-prometheusrule.yaml` for the model and its baseline in
[`gpu-node/real-gpu-results.md`](gpu-node/real-gpu-results.md). It only
resolves on the GPU cluster; the local kind cluster has no real GPU to meter.

## Dashboards & alerts

- **Grafana:** dashboard uid `llm-inference` (TTFT, ITL, throughput, queue,
  KV-cache, replicas, cost/1M tokens, error-budget burn rate). `make grafana`
  → http://localhost:3000 (admin/admin).
- **Alerts:**
  - `InferenceTTFTSLOBreach` — TTFT p95 > 1 s for 5m.
  - `InferenceQueueBacklog` — waiting > 5 for 2m.
  - `InferenceTTFTErrorBudgetFastBurn` — TTFT burn rate > 14.4x over both the
    1h and 5m windows for 2m (30-day budget gone in ~2h; page).
  - `InferenceTTFTErrorBudgetSlowBurn` — TTFT burn rate > 6x over both the 6h
    and 30m windows for 15m (sustained degradation; ticket).
  - `InferenceCostBudgetBreach` — cost/1M tokens > $0.01 for 15m.

## Common operations

- **See the autoscaler:** `kubectl get scaledobject,hpa -n inference`
- **Watch scaling live:** `kubectl get deploy/mock-vllm,hpa -n inference -w`
- **Tail engine logs:** `kubectl logs -l app=mock-vllm -n inference -f`
  (GPU: `-l serving.kserve.io/inferenceservice=qwen-vllm`)
- **Check scrape health:** Prometheus → Status → Targets (the `inference/...`
  ServiceMonitor should be UP).
- **Drive a load/scaling test:** `kubectl apply -f loadtest/incluster-load.yaml`

## Triage

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `InferenceTTFTSLOBreach` firing | Saturated; not enough replicas | Confirm HPA at `maxReplicas`; raise `maxReplicaCount` or per-replica KV headroom |
| Queue deep but replicas **not** scaling | KEDA can't read Prometheus | `kubectl describe scaledobject` / `hpa`; check `serverAddress` + that the metric exists in Prometheus |
| Scaled out but queue **still** growing | Traffic not load-balancing (pinned to one pod) | Route via the Service/gateway, not `port-forward`; verify `running` spreads across pods |
| Scrape target DOWN | label/selector mismatch | Check ServiceMonitor `release:` label and the Service port name |
| `InferenceTTFTErrorBudgetFastBurn`/`SlowBurn` firing | Same root causes as `InferenceTTFTSLOBreach`, caught earlier via a ratio of good-vs-total requests instead of a single-window threshold | Same triage as the TTFT breach; fast-burn pages, slow-burn is a ticket |
| `InferenceCostBudgetBreach` firing | GPU power draw high relative to throughput (saturation, thermal throttling, a stuck low-throughput regime) | Check `nvidia-smi`/DCGM for throttling and `job:vllm_tokens_per_second:1m` for a throughput collapse |

## Game-day: kill a pod mid-load

**Run 2026-08-27**, on a throwaway local `kind` cluster (2 replicas, KEDA's
steady state under load), driving 6 concurrent streams through the Service
(not `kubectl port-forward` — see below) and deleting one running pod
mid-traffic. Full method, raw logs, and numbers:
[`local/runs/2026-08-27-gameday/`](local/runs/2026-08-27-gameday/README.md).

**Result:**

- **0 failed requests** out of 396 — the Service dropped the terminating
  pod's endpoint and load-balanced onto the survivor; no client-visible
  errors during the outage.
- The survivor pod ran ~2x slower while carrying both pods' load alone (mean
  1.19s vs. a 0.89s baseline, max 1.63s) — a real capacity dip, not a
  failure. On a busier cluster this is exactly what
  `InferenceTTFTErrorBudgetFastBurn` exists to catch.
- The replacement pod's `Ready` condition flipped **10s** after the delete;
  latency was back to baseline within ~12s of the kill.

**Postmortem — one real finding, one confirmed assumption:**

1. **Finding:** the first attempt at this drill used `kubectl port-forward
   svc/mock-vllm` as the load path and it produced a wall of connection
   errors after the kill, not a clean failover. `port-forward` to a Service
   resolves to one backing pod once and doesn't follow Service endpoint
   changes — killing that pod breaks the tunnel outright. This is already
   the "route via the Service/gateway, not `port-forward`" line in the
   triage table below; the drill is direct confirmation of why that line is
   there. Re-running the load generator as an in-cluster Pod hitting the
   Service DNS name (real load-balanced traffic) is what produced the clean
   zero-downtime result above.
2. **Confirmed:** replica count of 1 (the Deployment's un-scaled default) has
   no redundancy — killing the only pod would have caused a request gap for
   the ~10s it takes a replacement to become Ready. `minReplicaCount: 1` on
   the ScaledObjects means this is a real, accepted risk at zero load; it's
   why the KEDA-driven replica count matters as much as the recovery being
   automatic.
