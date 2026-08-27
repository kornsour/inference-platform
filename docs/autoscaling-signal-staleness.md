# Signal staleness in the autoscaling control loop

The [write-up](../phase-2-capstone/WRITEUP.md) shows KEDA scaling out correctly on the
queue-depth signal. What it doesn't show is that the replica count at any instant reflects
saturation as it was **some tens of seconds ago**, not right now. That's not a bug — it's a
consistency property of any control loop built on scrape-and-poll — but it was previously
undocumented and unmeasured. This page makes it a number instead of something reasoned about
from the configured intervals alone.

## The lag chain

Five independently-clocked layers sit between "the GPU is saturated" and "there is another
pod":

1. **vLLM updates its gauges continuously**, in-process, on every scheduler step. No lag here.
2. **Prometheus scrapes on its `scrape_interval`.** A gauge that changed the instant *after*
   a scrape has to wait a full interval to be observed. Worst case: the whole interval.
3. **KEDA polls Prometheus on the ScaledObject's `pollingInterval`** — for both trigger
   flavors this repo uses: the built-in `prometheus` trigger (`local/manifests/scaledobject.yaml`,
   `gpu-node/keda-scaledobject-gpu.yaml`, `k8s/keda-scaledobject.yaml`) and the custom
   external scaler's `GetMetrics` path (`keda-inference-scaler/deploy/scaledobject-external.yaml`).
   Worst case: a fresh Prometheus sample that lands right after a poll waits a full
   `pollingInterval` for the next one.
4. **The external scaler's own `StreamIsActive` ticker** ([`main.go`](../phase-2-capstone/keda-inference-scaler/main.go))
   runs an *independent* poll of its own, on `streamPollInterval` (10s by default,
   [`internal/config/config.go`](../phase-2-capstone/keda-inference-scaler/internal/config/config.go)),
   used for activation rather than the metric value the HPA scales on. It shares nothing with
   `pollingInterval` — no shared clock, no shared cache invalidation trigger — so the two can
   drift in and out of phase with each other independently.
5. **The HPA's `scaleDown.stabilizationWindowSeconds`** holds off scaling *in* for that long
   after the last time the metric justified a larger replica count. This doesn't make the
   *signal* any older, but it does make the *reaction* to a since-recovered signal lag by up
   to the window's length — worth naming in the same breath as the others because it's the
   same shape of problem (a decision made on a timer, not on the event itself).

None of these layers know about each other. `pollingInterval` isn't derived from
`scrape_interval`; `streamPollInterval` isn't derived from either. That's the real finding:
the staleness isn't one number that falls out of a single config value, it's the result of
up to four uncoordinated clocks landing wherever they land relative to each other.

## Worst-case signal age

For the metric *value* a scaling decision acts on (steps 2–3 above), the worst case is
additive:

```
worst_case_signal_age = scrape_interval + pollingInterval
```

A fresh event has to wait up to a full `scrape_interval` to reach Prometheus, then up to a
full `pollingInterval` for KEDA's next poll to fetch it. (The external scaler's `CacheTTL`,
15s by default, doesn't add to this in the worst case — see
[Instrumentation](#instrumentation-scaler_signal_age_seconds) below for why a cache hit
doesn't reset the clock.) The `StreamIsActive` ticker (step 4) adds a *second*, independent
bound of the same shape for the activation decision specifically:
`worst_case_activation_age = scrape_interval + streamPollInterval`.

Working through this repo's actual configured values, before this issue:

| ScaledObject | scrape interval | `pollingInterval` | worst-case signal age | `streamPollInterval` | notes |
|---|---:|---:|---:|---:|---|
| `local/manifests/scaledobject.yaml` (mock, built-in trigger) | 10s ([`servicemonitor.yaml`](../phase-2-capstone/local/manifests/servicemonitor.yaml)) | *unset* → KEDA default **30s** | **40s** | n/a | relies on an undocumented default |
| `gpu-node/keda-scaledobject-gpu.yaml` (real GPU, built-in trigger) | 15s ([`observability.yaml`](../phase-2-capstone/gpu-node/observability.yaml)) | **15s** | 30s | n/a | `pollingInterval == scrape_interval` — see [Oscillation](#oscillation) |
| `keda-inference-scaler/deploy/scaledobject-external.yaml` (external scaler) | 15s | **15s** | 30s | *unset* → scaler default **10s** | both the poll and the ticker sit at or below the scrape interval |
| `k8s/keda-scaledobject.yaml` (production KServe template) | 15s ([`podmonitor.yaml`](../phase-2-capstone/k8s/podmonitor.yaml)) | *unset* → KEDA default 30s | 45s | n/a | already in the safe zone by accident |

Two of these four are already sitting in a genuinely bad configuration, not a hypothetical
one -- see below.

## Oscillation

> "If `pollingInterval` is short relative to the scrape interval, the scaler repeatedly reads
> the *same* Prometheus sample and can act on it more than once."

That's not a hypothetical for this repo. `gpu-node/keda-scaledobject-gpu.yaml` and
`keda-inference-scaler/deploy/scaledobject-external.yaml` both set `pollingInterval: 15`
against a 15s scrape interval — `pollingInterval == scrape_interval` exactly. Two clocks at
the *same* period don't average out; depending on phase, a poll can land just before each new
scrape (repeatedly re-reading last interval's sample and potentially reinforcing a decision
that was already acted on) or just after (closer to the intended one-poll-per-sample
cadence). Which one you get is an accident of when the two loops started, not something the
config expresses or guarantees.

The external scaler's `StreamIsActive` ticker made this worse on its own terms:
`streamPollInterval` defaults to 10s, *below* the 15s scrape interval it's reading from — so
by construction, most ticks observe a sample that hasn't changed since the previous tick.

## Cold-start interaction

> "A vLLM pod that is scheduled but still loading weights contributes no capacity while
> already counting as a replica."

This one is named here rather than measured. The [metrics-faithful mock](../phase-2-capstone/local/mock-vllm/app.py)
starts serving in well under a second — it has no weight-loading phase to model, so a
scale-out in the mock genuinely adds capacity roughly as fast as the pod becomes `Ready`.
That's a real, acknowledged gap between the mock and a real vLLM pod loading a multi-GB
checkpoint onto a GPU, where the pod can count toward `replicas` (and even toward
`Ready`, depending on the readiness probe) well before it can absorb any of the queue.
Reproducing this faithfully needs either a real model load or a deliberately-lengthened
startup phase injected into the mock, neither of which this change adds — recorded here as
a documented limitation rather than silently glossed over.

## Instrumentation: `scaler_signal_age_seconds`

The external scaler now threads the *Prometheus sample's own timestamp* — not the time the
query ran — through every query it makes
([`internal/metrics.Sample`](../phase-2-capstone/keda-inference-scaler/internal/metrics/metrics.go)),
and reports the resulting age two ways at the moment each scaling decision is made:

- **A Prometheus gauge**, `scaler_signal_age_seconds{namespace,scaledobject,dimension}`
  (`dimension` is `queue` or `kv`), scraped by the new ServiceMonitor in
  [`deploy/scaler.yaml`](../phase-2-capstone/keda-inference-scaler/deploy/scaler.yaml) — this
  is what makes staleness something you can chart in Grafana over time, rather than
  something inferred from the configured intervals.
- **Structured log fields**, `queueSignalAgeSeconds`/`kvSignalAgeSeconds`, on every
  `IsActive`/`GetMetrics`/`StreamIsActive` log line.

A cache hit (within the external scaler's `CacheTTL`) returns the *original* sample,
timestamp included, so the reported age keeps growing across cache hits instead of resetting
to zero on every call — the cache is a link in the staleness chain, not an escape from it. A
dimension that read `metrics.ErrMissing` (and wasn't treated as an error) reports age `0`
rather than a bogus multi-year duration derived from a zero `time.Time` — the same
absent-vs-idle ambiguity `TreatMissingAsError` already exists to resolve for the value itself.

This only instruments the **external scaler path**. The built-in KEDA `prometheus` trigger
(what `local/`, `gpu-node/keda-scaledobject-gpu.yaml`, and `k8s/keda-scaledobject.yaml`
actually run) has no equivalent hook — KEDA's built-in scaler doesn't expose the sample
timestamp it read. For those, this document's worst-case formula is the available tool;
per-decision measurement would need either an upstream KEDA change or switching those
ScaledObjects to the external scaler.

## Recommended relationship

Given the lag chain above, three rules, applied as a floor (a config can be *more*
conservative than this without being wrong; being *less* conservative reproduces the
oscillation this document measures):

1. **`pollingInterval` should be a small multiple of `scrape_interval`, never equal to it.**
   Equal periods are exactly the resonance case in [Oscillation](#oscillation): whichever
   phase relationship the two loops happen to start with is locked in, unmonitored, for the
   life of the ScaledObject. A factor of ~2x keeps most decisions acting on a sample no more
   than one scrape old, without hammering Prometheus faster than its own data refreshes.
2. **`streamPollInterval` follows the same rule, independently** — it's a separate,
   uncoordinated clock reading the same underlying data, not a sub-interval of
   `pollingInterval`.
3. **`scaleDown.stabilizationWindowSeconds` should be at least `2 × worst_case_signal_age`**
   (`2 × (scrape_interval + pollingInterval)`) — long enough that a scale-in decision isn't
   itself reacting to a signal that's within one lag-cycle of being stale, without being so
   long that recovered capacity sits idle by default (Kubernetes' own default, 300s, is
   already far more conservative than this floor requires for every ScaledObject in this
   repo).

Applied to the four configs above:

| ScaledObject | `pollingInterval` (before → after) | `streamPollInterval` (before → after) | `stabilizationWindowSeconds` (before → after) |
|---|---|---|---|
| `local/manifests/scaledobject.yaml` | *(default) 30s* → **20s**, made explicit | n/a | 60s (already ≥ 2×(10+20)=60 — unchanged) |
| `gpu-node/keda-scaledobject-gpu.yaml` | **15s → 30s** | n/a | *(default) 300s* → **90s** (= 2×(15+30)) |
| `keda-inference-scaler/deploy/scaledobject-external.yaml` | **15s → 30s** | *(default) 10s* → **30s** | *(default) 300s* → **90s** |
| `k8s/keda-scaledobject.yaml` | *(default) 30s* → **30s**, made explicit | n/a | 300s (already ≥ 2×(15+30)=90 — unchanged, deliberately conservative per the file's own comment) |

`local`'s scrape interval (10s) is deliberately kept faster than the GPU paths' (15s) — it
costs nothing against a mock, and the shorter interval is what makes the "well below /
equal / well above" regimes in the next section land on clean, reproducible numbers (3s,
10s, 30s against a 10s scrape).

## Reproducing the regimes

The issue asks for the three `pollingInterval` regimes (well below, equal to, well above
`scrape_interval`) reproduced against the metrics-faithful mock, with replica count charted
against queue depth over time for each. [`loadtest/staleness-demo.sh`](../phase-2-capstone/loadtest/staleness-demo.sh)
implements that: it drives a step-function load (idle → sustained burst → stop) against the
mock, sampling queue depth, KV-cache %, and replica count from Prometheus every 2 seconds,
for a given `POLLING_INTERVAL`, and prints the same kind of Markdown timeline
`scale-demo.sh` does.

```bash
cd phase-2-capstone/local && make up   # bring up kind + KEDA + kube-prometheus-stack + the mock
cd ../loadtest
POLLING_INTERVAL=3  ./staleness-demo.sh | tee below.md    # well below the 10s scrape interval
POLLING_INTERVAL=10 ./staleness-demo.sh | tee equal.md    # equal to it
POLLING_INTERVAL=30 ./staleness-demo.sh | tee above.md    # well above it
```

**This PR does not include a captured run.** Bringing up a second full kind + KEDA +
kube-prometheus-stack stack while this issue was being worked meant sharing a Docker daemon
that was, at the time, already visibly saturated by concurrent local clusters and
containers stuck in `Created` state rather than running — spinning up another full stack on
top of that risked degrading everyone else's work for a result that would just have been
numbers pasted into a table. Rather than fabricate plausible-looking replica/queue-depth
data to fill that gap, this section documents the methodology and ships the script; the
[write-up](../phase-2-capstone/WRITEUP.md) will get the actual regime charts appended once
it's run for real, on a quiet Docker daemon.
