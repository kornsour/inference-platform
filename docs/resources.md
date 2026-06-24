# Resources

A curated, opinionated reading, watching, and listening list for **LLM inference serving**, the platform layer this project is about. It is not exhaustive. Every entry earns its place because it teaches something that transfers to serving models at scale. Annotations say why it matters for a platform, in the spirit of [the glossary](glossary.md).

> Legend: :material-rocket-launch-outline: start here · :material-microscope: deep / technical · :material-cash-multiple: economics & capacity · :material-compass-outline: leadership & strategy

---

## Foundational papers

The primary sources behind the vocabulary. Read the abstract and figures of each; you don't need every proof.

- :material-rocket-launch-outline: **Attention Is All You Need** (Vaswani et al., 2017): the Transformer. The architecture everything below serves. [arXiv:1706.03762](https://arxiv.org/abs/1706.03762)
- :material-microscope: **Efficient Memory Management for LLM Serving with PagedAttention** (Kwon et al., SOSP 2023): the vLLM paper. Explains why KV-cache fragmentation is the real concurrency ceiling and how paging fixes it. The single most important systems paper for this project. [arXiv:2309.06180](https://arxiv.org/abs/2309.06180)
- :material-microscope: **Orca: A Distributed Serving System for Transformer-Based Generative Models** (Yu et al., OSDI 2022): introduced continuous (iteration-level) batching, the biggest throughput win in modern serving. [Paper](https://www.usenix.org/conference/osdi22/presentation/yu)
- :material-microscope: **FlashAttention** (Dao et al., 2022): IO-aware exact attention, and why memory bandwidth, not FLOPs, often dominates. [arXiv:2205.14135](https://arxiv.org/abs/2205.14135)
- :material-microscope: **DistServe: Disaggregating Prefill and Decoding** (Zhong et al., OSDI 2024): the case for splitting prefill and decode onto separate GPU pools because they have opposite bottlenecks. The architecture behind NVIDIA Dynamo and llm-d. [arXiv:2401.09670](https://arxiv.org/abs/2401.09670)
- :material-microscope: **Splitwise: Efficient Generative LLM Inference Using Phase Splitting** (Patel et al., Microsoft, ISCA 2024): disaggregation from a fleet and economics angle. [arXiv:2311.18677](https://arxiv.org/abs/2311.18677)
- :material-microscope: **SARATHI / Chunked Prefill** (Agrawal et al., 2023): how chunking prefill smooths the prefill-vs-decode interference that hurts tail latency. [arXiv:2308.16369](https://arxiv.org/abs/2308.16369)
- :material-microscope: **SGLang: Efficient Execution with RadixAttention** (Zheng et al., 2023): prefix-cache reuse for structured and high-concurrency workloads. [arXiv:2312.07104](https://arxiv.org/abs/2312.07104)

## Books

- :material-rocket-launch-outline: :material-compass-outline: **AI Engineering**, Chip Huyen (O'Reilly, 2025). The current best single book on building products on top of foundation models: evaluation, latency and cost trade-offs, inference optimization, serving. Closest to this project's center of gravity.
- :material-compass-outline: **Designing Machine Learning Systems**, Chip Huyen (O'Reilly, 2022). The ML-platform companion: deployment, monitoring, infrastructure, the production lifecycle.
- :material-rocket-launch-outline: **Designing Data-Intensive Applications**, Martin Kleppmann (O'Reilly). Not AI-specific, but the canonical text for the distributed-systems reasoning (throughput vs latency, batching, backpressure, capacity) that is the platform job.
- :material-microscope: **Build a Large Language Model (From Scratch)**, Sebastian Raschka (Manning, 2024). Build the thing you serve, in PyTorch. Demystifies prefill/decode and the KV cache by making you implement them.
- :material-cash-multiple: **Site Reliability Engineering**, Beyer et al. (Google, free online). SLOs, error budgets, and capacity planning, directly reusable as inference SLIs (TTFT/goodput) and on-call discipline. <https://sre.google/books/>

## Blogs, guides, and long-form writing

- :material-rocket-launch-outline: **Anyscale, "How continuous batching enables 23x throughput in LLM inference":** the clearest single explainer of continuous batching with numbers. <https://www.anyscale.com/blog/continuous-batching-llm-inference>
- :material-rocket-launch-outline: :material-microscope: **Lilian Weng, "Large Transformer Model Inference Optimization":** a dense, well-cited survey of the whole optimization space (quantization, distillation, sparsity, batching). <https://lilianweng.github.io/posts/2023-01-10-inference-optimization/>
- :material-microscope: :material-cash-multiple: **kipp.ly, "Transformer Inference Arithmetic":** back-of-the-envelope math for latency, memory, and cost per token. The mental model for capacity planning. <https://kipply.github.io/blog/transformer-inference-arithmetic/>
- :material-microscope: **vLLM Blog:** release notes and deep dives from the engine you'll run first. <https://blog.vllm.ai/>
- :material-microscope: **NVIDIA Technical Blog (Inference):** TensorRT-LLM, Triton, and Dynamo internals from the hardware vendor. <https://developer.nvidia.com/blog/category/generative-ai/>
- :material-cash-multiple: **Baseten / Modal / Fireworks engineering blogs:** practitioner write-ups on cold starts, autoscaling, and cost-per-token from companies whose whole business is serving. (Search their blogs for "LLM inference".)
- :material-rocket-launch-outline: **Hugging Face Blog:** accessible explainers (TGI internals, quantization, GPU memory). <https://huggingface.co/blog>
- :material-compass-outline: **Sebastian Raschka, "Ahead of AI":** a newsletter that keeps you current on models and methods without the hype. <https://magazine.sebastianraschka.com/>

## Podcasts

- :material-rocket-launch-outline: :material-compass-outline: **Latent Space** (swyx & Alessio): the most infra- and serving-literate AI pod, with frequent episodes featuring inference-engine and platform builders. <https://www.latent.space/podcast>
- :material-microscope: **The TWIML AI Podcast** (Sam Charrington): long, technical interviews with good coverage of systems and MLOps.
- :material-rocket-launch-outline: **Practical AI** (Changelog): applied, infrastructure-flavored, approachable.
- :material-compass-outline: **No Priors** / **Gradient Dissent** (Weights & Biases): strategy and practitioner angles on where the field is going.

## YouTube and video courses

- :material-rocket-launch-outline: **Andrej Karpathy, "Deep Dive into LLMs like ChatGPT"** and **"Let's build GPT from scratch":** the best on-ramp to how these models actually run. <https://www.youtube.com/@AndrejKarpathy>
- :material-rocket-launch-outline: **3Blue1Brown, Neural Networks / Transformers series:** the visual intuition for attention. <https://www.youtube.com/@3blue1brown>
- :material-microscope: **GPU MODE** (formerly CUDA MODE): lectures on GPU kernels, performance, and the systems layer under inference. <https://www.youtube.com/@GPUMODE>
- :material-microscope: **vLLM Office Hours:** recurring deep dives with the maintainers on batching, scheduling, and disaggregation. (Search "vLLM Office Hours" on YouTube.)
- :material-microscope: **Stanford CS25: Transformers United:** guest lectures from the people building the field. <https://web.stanford.edu/class/cs25/>
- :material-microscope: **Stanford CS336: Language Modeling from Scratch:** build a small LM and its serving stack end to end, with lectures on YouTube.

## Docs to keep open (the tools you'll actually run)

- **vLLM:** <https://docs.vllm.ai>
- **KServe** (`LLMInferenceService`): <https://kserve.github.io/website/>
- **Ray Serve:** <https://docs.ray.io/en/latest/serve/index.html>
- **KEDA** (event-driven, inference-aware autoscaling): <https://keda.sh/docs/>
- **NVIDIA Dynamo:** <https://github.com/ai-dynamo/dynamo>
- **llm-d** (Kubernetes-native distributed inference): <https://llm-d.ai/>
- **Prometheus** / **Grafana:** <https://prometheus.io/docs/> · <https://grafana.com/docs/>
- **Locust** (load testing): <https://docs.locust.io/>

## Communities

- **GPU MODE** Discord: the active hub for GPU and inference performance work.
- **vLLM** GitHub Discussions and Slack: the closest thing to office hours for the engine.
- **r/LocalLLaMA:** fast-moving signal on quantization, hardware, and running models cheaply.
- **CNCF Slack** (`#kserve`, `#keda`): the Kubernetes-serving operators.

---

*Suggestions welcome: open an issue or PR. Keep the bar high. Each entry should teach something that transfers to serving models at scale, and say why.*
