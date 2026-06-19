# Building an autoscaling LLM inference platform on Kubernetes

> The public portfolio artifact. Polish this into a repo README or blog post and
> publish from your existing GitHub presence. It is the spine of the technical
> interview track — write it so a hiring manager can see how you think.

## TL;DR
*(2–3 sentences: what you built, the one non-obvious thing you learned, the headline number.)*

## Why inference autoscaling is different
*(CPU is the wrong signal. Explain KV-cache utilization / queue depth / TTFT as the real saturation signals. This is the insight the role is testing for.)*

## Architecture
*(Diagram + the layers: gateway → KServe/vLLM → Prometheus → KEDA. Why each choice. Link the manifests.)*

## Autoscaling on an inference-aware signal
*(The KEDA ScaledObject. What metric, what threshold, why. Show the replica count reacting to load in a screenshot.)*

## Load test & results
*(How you drove it, where it saturated.)*

| concurrency / users | TTFT p95 | total tok/s | replicas | notes |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Cost
*(GPU instance $/hr → cost-per-million-tokens at the throughput you measured. The unit economic. Tie to capacity/headroom trade-offs.)*

## Reliability
*(SLO defined, alert wired, game-day result. Link the runbook and postmortem.)*

## What I'd do next with more budget
*(Disaggregated prefill/decode on separate pools, multi-region, quantization, larger model, canary automation. Shows you can reason about scale you didn't operate.)*

## Honest scope
*(Self-directed deep dive at small scale — demonstrates how I learn and lead, not equivalent to years of production operation. This honesty reads as senior.)*
