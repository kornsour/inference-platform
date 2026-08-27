# GPU run provenance

Raw evidence for the real-GPU numbers quoted in
[`../real-gpu-results.md`](../real-gpu-results.md), so each figure traces back to a
command, a date, and captured output instead of being transcribed by hand. This
mirrors the convention already used for the local mock-vLLM evidence (see
[`../../local/runs/2026-08-27-scale-out/README.md`](../../local/runs/2026-08-27-scale-out/README.md)
for an example), applied to the physical two-GPU cluster.

## Layout

One directory per run, named `<date>-<run-name>/` (e.g. `2026-08-27-3b-kv-saturation/`),
containing:

| File | What it is |
| --- | --- |
| `command.txt` | The exact `gpu-loadtest.py` invocation — concurrency, duration, `--base-path`, model — plus the vLLM server flags (`--gpu-memory-utilization`, `--max-model-len`, `--enforce-eager`, etc.) it was run against. |
| `stdout.log` | Raw stdout of that `gpu-loadtest.py` run (client-side TTFT percentiles and throughput). |
| `nvidia-smi.log` | `nvidia-smi` output captured on the serving node while the load was running (power draw, utilization, memory). |
| `vllm-metrics.prom` | The raw `curl <node>:8000/metrics` scrape at peak load — the server-side cross-check (`vllm:gpu_cache_usage_perc`, `vllm:num_requests_waiting`, `vllm:generation_tokens_total`, …) that the Method note in `real-gpu-results.md` refers to. |
| `image-digest.txt` | The vLLM image digest the run used (`docker inspect --format='{{index .RepoDigests 0}}' <image>` or the equivalent `crictl`/`kubectl` lookup), so the exact engine build is pinned. |
| `README.md` | Short human summary of the run — what it shows, any caveats — same as `../../local/runs/*/README.md`. |

[`capture-run.sh`](capture-run.sh) automates writing the first four files for a new run;
see its `--help` for usage.

## Status

This convention did not exist when Runs 1–4 in `real-gpu-results.md` were captured, and
the raw `nvidia-smi`/`vLLM`-scrape/stdout output from those sessions was not retained
outside the derived numbers already written into that file — there is nothing genuine to
commit here for them without re-running the benchmarks on the physical two-GPU cluster.
Backfilling those four runs, and adding the date + run-directory link to each table
caption in `real-gpu-results.md` as called for in
[#5](https://github.com/kornsour/inference-platform/issues/5), is left as follow-up work
to do from the GPU nodes themselves. Every run captured **from here on** must land in this
directory before its numbers go into `real-gpu-results.md`.
