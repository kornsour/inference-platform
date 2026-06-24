# OSS contribution — submitted

The Phase 2 checklist calls for landing **one small PR to an OSS inference project**. We
did it by contributing the custom [KEDA external scaler](keda-inference-scaler/README.md) —
built for this capstone — to KEDA's community registry.

| | |
|---|---|
| **PR** | [kedacore/external-scalers#34](https://github.com/kedacore/external-scalers/pull/34) (draft) |
| **What it adds** | one entry to the "Scalers from the community" list, pointing at the scaler repo |
| **Published scaler** | [github.com/kornsour/keda-inference-scaler](https://github.com/kornsour/keda-inference-scaler) (public, Apache-2.0, CI) |
| **Status** | DCO ✅, task-list ✅, link resolves ✅ — awaiting "Ready for review" |

## Why a standalone public repo (and not this one)

`kedacore/external-scalers` is a **community index, not a code monorepo** — every entry
links to a scaler hosted in its *own* repo (e.g. `balchua/artemis-ext-scaler`,
`devjoes/github-runner-autoscaler`). So the scaler needed a public home, and **this capstone
repo is private** — it holds private career-strategy material — so it can't be the source.

The fix was to publish the scaler as its **own standalone public repo**,
[`kornsour/keda-inference-scaler`](https://github.com/kornsour/keda-inference-scaler):

- **Purpose:** give the scaler a public, installable home so the community-list entry
  resolves and others can actually use it (its CI publishes an image to GHCR).
- **Why it's needed:** the list links externally (convention) *and* a private link would be
  dead for reviewers — so a private subdirectory link would have been rejected.
- **What's in it:** just the scaler — Go source, proto, Dockerfile, tests, CI, deploy
  manifests, Apache-2.0 license. Genericized (no home-LAN specifics). Nothing private is
  exposed; the in-repo copy under [`keda-inference-scaler/`](keda-inference-scaler/README.md)
  remains the capstone's working copy.

## Why a one-line PR is the *complete* change

Because the target repo is an index, the entire correct contribution is **a single bullet**:

```diff
+ - LLM inference (vLLM KV-cache + request-queue saturation) ([GitHub](https://github.com/kornsour/keda-inference-scaler))
```

The substance — the scaler implementation a maintainer reviews — lives in the linked repo,
not in `external-scalers`. (Contributing a *built-in* scaler into `kedacore/keda` core would
be a much larger code PR; the project deliberately steers external scalers to the
community-hosted model used here.)

## Why it counts

A genuine upstream contribution to a **CNCF** project in the exact domain of the role,
backed by working, tested, CI-built code you can speak to in depth — not a drive-by typo
fix. Once merged, link it from the [write-up](WRITEUP.md).

## Remaining (manual)

1. Review the scaler repo + PR, then flip **#34** from draft → **Ready for review**.
2. Any further commits to the PR branch need `git commit -s` (KEDA enforces DCO sign-off).
