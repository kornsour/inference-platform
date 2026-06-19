# Runbook — <platform name>

> Operational guide for the inference platform. Keep it short and real.
> Pair this with one game-day exercise (kill a pod mid-load) and a postmortem.

## Service overview
- **What it serves:** <model(s)>, OpenAI-compatible endpoint at <url>.
- **Topology:** Envoy AI Gateway → KServe InferenceService (vLLM) → GPU pods.
- **Owner / on-call:** <you>.

## SLOs
| SLI | Objective | Where to see it |
| --- | --- | --- |
| TTFT p95 | < 1s over rolling 5m | Grafana: <dashboard link> |
| Availability | 99.9% | <...> |
| Error rate | < 1% | <...> |

## Dashboards & alerts
- Grafana dashboard: <link>
- Alert: TTFT p95 SLO burn → <where it fires>

## Common operations
- **Scale manually:** `kubectl scale deploy/qwen-vllm-predictor --replicas=N -n inference`
- **Check autoscaler:** `kubectl get scaledobject,hpa -n inference`
- **Tail engine logs:** `kubectl logs -l serving.kserve.io/inferenceservice=qwen-vllm -n inference -f`

## Failure playbooks
### High TTFT / SLO burn
1. Check queue depth (`vllm:num_requests_waiting`) and KV-cache util.
2. Confirm KEDA scaled out; if pinned at maxReplicas, you're GPU-bound — add capacity or shed load at the gateway.

### Pod crash / GPU OOM
1. Symptom: pod restarts, `gpu-memory-utilization` too high for `max-model-len`.
2. Lower `--gpu-memory-utilization` or `--max-model-len`; redeploy.

## Game-day log
*(Record the exercise: killed a pod mid-load at <time>, observed <graceful degradation / requests rerouted / replica replaced in Ns>. Link the postmortem.)*
