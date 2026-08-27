# Game-day run — 2026-08-27

Executed the runbook's planned game-day for real, on a throwaway local `kind`
cluster (`inference-platform-issue8`, deleted after the run — not the
persistent `inference-platform` cluster other work uses).

## Method

1. `kind create cluster`, build + `kind load` the `mock-vllm:local` image,
   apply `manifests/deployment.yaml` + `manifests/service.yaml`.
2. `kubectl -n inference scale deployment/mock-vllm --replicas=2` (this is
   what KEDA maintains once real load is flowing; scaled directly here since
   this drill didn't stand up the full KEDA/Prometheus stack).
3. Load generator: a small Python script (6 concurrent workers, `max_tokens:
   10` per request) run **as an in-cluster Pod** hitting
   `http://mock-vllm.inference.svc.cluster.local:8000`, not `kubectl
   port-forward` — port-forward pins to a single pod IP and does not fail
   over when that pod dies (confirmed by a first attempt: switching to
   in-cluster traffic through the Service was required to see real
   load-balanced failover, which is exactly the "route via the Service, not
   port-forward" lesson already in the runbook's triage table).
4. Mid-load, deleted one of the two running pods
   (`kubectl delete pod <name>`, no `--grace-period=0`) and kept the load
   running through the replacement pod becoming Ready.
5. Captured `kubectl -n inference get pods -w` (`pods-watch.log`) and every
   request's wall-clock time / status / latency (`loadgen.log`) across the
   whole window.

## Raw evidence

- [`loadgen.log`](loadgen.log) — 396 requests, `{wall_time} worker={n}
  status={code} elapsed_s={latency}` per line.
- [`pods-watch.log`](pods-watch.log) — `kubectl get pods -w` output spanning
  the kill and replacement.

## Result (summarized in `runbook.md`)

- **0 failed requests** out of 396 — the Service's endpoint list dropped the
  terminating pod and load-balanced onto the survivor; no client-visible
  errors.
- Requests landing on the survivor pod during the gap ran ~2x slower (mean
  1.19s vs. a 0.89s baseline, max 1.63s) while it absorbed both pods' traffic
  alone — a real capacity dip, not a failure.
- The replacement pod's `Ready` condition flipped exactly **10s** after the
  delete (`18:00:49Z` → `18:00:59Z`, per `kubectl get pod -o
  jsonpath='{.status.conditions}'`), and latency was back to baseline within
  ~12s of the kill.
