# Building an autoscaling LLM inference platform on Kubernetes

> The public portfolio artifact. Polish this into a repo README or blog post and
> publish it. Write it so a reader can follow how the platform works and why each
> choice was made.

## TL;DR
*(2–3 sentences: what I built, the one non-obvious thing I learned, the headline number.)*

## Why inference autoscaling is different
*(CPU is the wrong signal. Explain KV-cache utilization, queue depth, and TTFT as the real saturation signals.)*

## Architecture
*(Diagram plus the layers: gateway, KServe/vLLM, Prometheus, KEDA. Why each choice. Link the manifests.)*

## Autoscaling on an inference-aware signal
*(The KEDA ScaledObject. What metric, what threshold, why. Show the replica count reacting to load in a screenshot.)*

## Load test and results
*(How I drove it, where it saturated.)*

| concurrency / users | TTFT p95 | total tok/s | replicas | notes |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Cost
*(GPU instance $/hr converted to cost-per-million-tokens at the throughput measured. The unit economic. Tie it to capacity and headroom trade-offs.)*

## Reliability
*(SLO defined, alert wired, game-day result. Link the runbook and postmortem.)*

## What I'd do next with more budget
*(Disaggregated prefill/decode on separate pools, multi-region, quantization, a larger model, canary automation.)*

## Honest scope
*(A self-directed deep dive at small scale, not equivalent to years of production operation. Name what the homelab can and can't show.)*
