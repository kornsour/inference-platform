# AI Inference

A self-directed learning project to build genuine, hands-on depth in **LLM inference serving** — the platform layer underneath generative AI models: GPU scheduling, high-throughput serving engines, inference-aware autoscaling, and the observability and economics of running models at scale.

It is structured as a 6-month program aligned to a specific target role: **Principal Engineering Manager, GitHub Copilot AI Inference Platform**. The full strategy, gap analysis, and milestone tracking live in [`docs/project-plan.md`](docs/project-plan.md).

## Why this exists

The honest framing: ~70% of the target role is platform engineering and leadership I already do (Kubernetes, GitOps, observability, SLOs, multi-tenant platforms, capacity/cost discipline). The other ~30% — generative AI *serving* infrastructure — is a real, specific gap. This repo closes it by building, not just reading: standing up real inference endpoints, then a real autoscaling platform on Kubernetes, and writing up the results as portfolio evidence.

## Structure

| Phase | Months | Theme | Folder |
| --- | --- | --- | --- |
| **1** | 1–2 | Inference serving foundations — vocabulary, economics, first local serve | [`phase-1-foundations/`](phase-1-foundations/) |
| **2** | 3–4 | Hands-on platform build — the capstone: autoscaling inference on Kubernetes | [`phase-2-capstone/`](phase-2-capstone/) |
| **3** | 5–6 | Scale, leadership, and application — positioning and interview prep | [`phase-3-positioning/`](phase-3-positioning/) |

Supporting docs:
- [`docs/project-plan.md`](docs/project-plan.md) — the full plan (gap analysis, roadmap, risks)
- [`docs/glossary.md`](docs/glossary.md) — inference serving vocabulary, the literacy target for Phase 1

## How to use it

1. Read [`docs/project-plan.md`](docs/project-plan.md) end to end once.
2. Block recurring weekly time (6–10 focused hours).
3. Work the phases in order. Each phase folder has its own README with a concrete checklist and the artifacts to produce.
4. The Phase 2 capstone is the highest-leverage work — protect that time. If something has to give, cut reading breadth, not the build.

## Progress

- [ ] **Phase 1** — Can explain prefill vs. decode and TTFT without notes; model served locally with measured TTFT / tokens-per-second; one-page brief written.
- [ ] **Phase 2** — Model on Kubernetes via KServe/Ray Serve + vLLM; KEDA autoscaling on an inference signal; Prometheus/Grafana dashboards; load test + public write-up.
- [ ] **Phase 3** — Scale & capacity study; reframed resume + positioning statement; leadership stories; ≥2 informational conversations; application submitted.
