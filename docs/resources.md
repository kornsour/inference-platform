# Resources

A curated, opinionated reading/watching/listening list for **LLM inference serving** — the platform layer this project is about. Not exhaustive; every entry earns its place because it teaches something that transfers to *serving models at scale*. Annotations say **why it matters for a platform**, in the spirit of [the glossary](glossary.md).

> Legend: 🟢 start here · 🔬 deep / technical · 💸 economics & capacity · 🧭 leadership & strategy

---

## Foundational papers

The primary sources behind the vocabulary. Read the abstract + figures of each; you don't need every proof.

- 🟢 **Attention Is All You Need** (Vaswani et al., 2017) — the Transformer. The architecture everything below serves. [arXiv:1706.03762](https://arxiv.org/abs/1706.03762)
- 🔬 **Efficient Memory Management for LLM Serving with PagedAttention** (Kwon et al., SOSP 2023) — the vLLM paper. Explains why KV-cache fragmentation is the real concurrency ceiling and how paging fixes it. The single most important systems paper for this project. [arXiv:2309.06180](https://arxiv.org/abs/2309.06180)
- 🔬 **Orca: A Distributed Serving System for Transformer-Based Generative Models** (Yu et al., OSDI 2022) — introduced **continuous (iteration-level) batching**, the biggest throughput win in modern serving. [Paper](https://www.usenix.org/conference/osdi22/presentation/yu)
- 🔬 **FlashAttention** (Dao et al., 2022) — IO-aware exact attention; why memory bandwidth, not FLOPs, often dominates. [arXiv:2205.14135](https://arxiv.org/abs/2205.14135)
- 🔬 **DistServe: Disaggregating Prefill and Decoding** (Zhong et al., OSDI 2024) — the case for splitting prefill and decode onto separate GPU pools because they have opposite bottlenecks. The architecture behind NVIDIA Dynamo and llm-d. [arXiv:2401.09670](https://arxiv.org/abs/2401.09670)
- 🔬 **Splitwise: Efficient Generative LLM Inference Using Phase Splitting** (Patel et al., Microsoft, ISCA 2024) — disaggregation from a fleet/economics angle. [arXiv:2311.18677](https://arxiv.org/abs/2311.18677)
- 🔬 **SARATHI / Chunked Prefill** (Agrawal et al., 2023) — how chunking prefill smooths the prefill-vs-decode interference that hurts tail latency. [arXiv:2308.16369](https://arxiv.org/abs/2308.16369)
- 🔬 **SGLang: Efficient Execution with RadixAttention** (Zheng et al., 2023) — prefix-cache reuse for structured / high-concurrency workloads. [arXiv:2312.07104](https://arxiv.org/abs/2312.07104)

## Books

- 🟢🧭 **AI Engineering** — Chip Huyen (O'Reilly, 2025). The current best single book on building products *on top of* foundation models: evaluation, latency/cost tradeoffs, inference optimization, serving. Closest to this project's center of gravity.
- 🧭 **Designing Machine Learning Systems** — Chip Huyen (O'Reilly, 2022). The ML-platform companion: deployment, monitoring, infrastructure, the production lifecycle.
- 🟢 **Designing Data-Intensive Applications** — Martin Kleppmann (O'Reilly). Not AI-specific, but the canonical text for the distributed-systems reasoning (throughput vs. latency, batching, backpressure, capacity) that *is* the platform job.
- 🔬 **Build a Large Language Model (From Scratch)** — Sebastian Raschka (Manning, 2024). Build the thing you serve, in PyTorch. Demystifies prefill/decode and the KV cache by making you implement them.
- 💸 **Site Reliability Engineering** — Beyer et al. (Google, free online). SLOs, error budgets, and capacity planning — directly reusable as inference SLIs (TTFT/goodput) and on-call discipline. <https://sre.google/books/>

## Blogs, guides & long-form writing

- 🟢 **Anyscale — "How continuous batching enables 23x throughput in LLM inference"** — the clearest single explainer of continuous batching with numbers. <https://www.anyscale.com/blog/continuous-batching-llm-inference>
- 🟢🔬 **Lilian Weng — "Large Transformer Model Inference Optimization"** — a dense, well-cited survey of the whole optimization space (quantization, distillation, sparsity, batching). <https://lilianweng.github.io/posts/2023-01-10-inference-optimization/>
- 🔬💸 **kipp.ly — "Transformer Inference Arithmetic"** — back-of-the-envelope math for latency, memory, and cost per token. The mental model for capacity planning. <https://kipply.github.io/blog/transformer-inference-arithmetic/>
- 🔬 **vLLM Blog** — release notes and deep dives from the engine you'll run first. <https://blog.vllm.ai/>
- 🔬 **NVIDIA Technical Blog (Inference)** — TensorRT-LLM, Triton, and Dynamo internals from the hardware vendor. <https://developer.nvidia.com/blog/category/generative-ai/>
- 💸 **Baseten / Modal / Fireworks engineering blogs** — practitioner write-ups on cold starts, autoscaling, and cost-per-token from companies whose whole business is serving. (Search their blogs for "LLM inference".)
- 🟢 **Hugging Face Blog** — accessible explainers (TGI internals, quantization, GPU memory). <https://huggingface.co/blog>
- 🧭 **Sebastian Raschka — "Ahead of AI"** — newsletter that keeps you current on models and methods without the hype. <https://magazine.sebastianraschka.com/>

## Podcasts

- 🟢🧭 **Latent Space** (swyx & Alessio) — the most infra- and serving-literate AI pod; frequent episodes with inference-engine and platform builders. <https://www.latent.space/podcast>
- 🔬 **The TWIML AI Podcast** (Sam Charrington) — long, technical interviews; good coverage of systems and MLOps.
- 🟢 **Practical AI** (Changelog) — applied, infrastructure-flavored, approachable.
- 🧭 **No Priors** / **Gradient Dissent** (Weights & Biases) — strategy and practitioner angles; useful for the leadership/positioning phase.

## YouTube & video courses

- 🟢 **Andrej Karpathy — "Deep Dive into LLMs like ChatGPT"** and **"Let's build GPT from scratch"** — the best on-ramp to how these models actually run. <https://www.youtube.com/@AndrejKarpathy>
- 🟢 **3Blue1Brown — Neural Networks / Transformers series** — the visual intuition for attention. <https://www.youtube.com/@3blue1brown>
- 🔬 **GPU MODE** (formerly CUDA MODE) — lectures on GPU kernels, performance, and the systems layer under inference. <https://www.youtube.com/@GPUMODE>
- 🔬 **vLLM Office Hours** — recurring deep dives with the maintainers on batching, scheduling, and disaggregation. (Search "vLLM Office Hours" on YouTube.)
- 🔬 **Stanford CS25: Transformers United** — guest lectures from the people building the field. <https://web.stanford.edu/class/cs25/>
- 🔬 **Stanford CS336: Language Modeling from Scratch** — build a small LM and its serving stack end to end; lectures on YouTube.

## Docs to keep open (the tools you'll actually run)

- **vLLM** — <https://docs.vllm.ai>
- **KServe** (`LLMInferenceService`) — <https://kserve.github.io/website/>
- **Ray Serve** — <https://docs.ray.io/en/latest/serve/index.html>
- **KEDA** (event-driven / inference-aware autoscaling) — <https://keda.sh/docs/>
- **NVIDIA Dynamo** — <https://github.com/ai-dynamo/dynamo>
- **llm-d** (Kubernetes-native distributed inference) — <https://llm-d.ai/>
- **Prometheus** / **Grafana** — <https://prometheus.io/docs/> · <https://grafana.com/docs/>
- **Locust** (load testing) — <https://docs.locust.io/>

## Communities

- **GPU MODE** Discord — the active hub for GPU/inference performance work.
- **vLLM** GitHub Discussions & Slack — closest thing to office hours for the engine.
- **r/LocalLLaMA** — fast-moving signal on quantization, hardware, and running models cheaply.
- **CNCF Slack** (`#kserve`, `#keda`) — the Kubernetes-serving operators.

---

*Suggestions welcome — open an issue or PR. Keep the bar high: each entry should teach something that transfers to serving models at scale, and say why.*
