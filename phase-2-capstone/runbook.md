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
| Availability | 99.9% | _TODO_ |
| Error rate | < 1% | _TODO_ |

SLIs are recording rules in [`local/manifests/slo-prometheusrule.yaml`](local/manifests/slo-prometheusrule.yaml).

## Dashboards & alerts

- **Grafana:** dashboard uid `llm-inference` (TTFT, ITL, throughput, queue,
  KV-cache, replicas). `make grafana` → http://localhost:3000 (admin/admin).
- **Alerts:** `InferenceTTFTSLOBreach` (TTFT p95 > 1 s for 5m),
  `InferenceQueueBacklog` (waiting > 5 for 2m).

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

## Game-day (planned)

Kill a pod mid-load (`kubectl delete pod -l app=mock-vllm -n inference --field-selector ...`)
and confirm the Service drops it, the Deployment replaces it, and TTFT recovers.
Pair with a short postmortem. _TODO: run + write up._
