# OSS contribution — closed, next attempt in progress

The Phase 2 checklist calls for landing **one small PR to an OSS inference project**. We
attempted it by contributing the custom [KEDA external scaler](keda-inference-scaler/README.md) —
built for this capstone — to KEDA's community registry.

| | |
|---|---|
| **PR** | [kedacore/external-scalers#34](https://github.com/kedacore/external-scalers/pull/34) — **closed 2026-08-16, not merged** |
| **What it added** | one entry to the "Scalers from the community" list, pointing at the scaler repo |
| **Published scaler** | [github.com/kornsour/keda-inference-scaler](https://github.com/kornsour/keda-inference-scaler) (public, Apache-2.0, CI) |
| **Outcome** | Marked "Ready for review" on 2026-06-24 and then closed by the author on 2026-08-16 with no maintainer review or comment in the ~7 weeks between. The head branch was deleted at close. There's no recorded maintainer objection to the scaler itself — the PR simply went stale. |

## Why it likely stalled

The `external-scalers` repo's own README doesn't actually point contributors at hand-edited
PRs to the "Scalers from the community" list as the primary path — it says: "Everyone is
encouraged to list their external scaler on **Artifact Hub**," and the KEDA docs site pulls
its "available external scalers" listing from Artifact Hub, not from that README section.
A raw README-list PR is a secondary, lower-traffic path with no CI or review SLA attached to
it, which is consistent with a PR sitting untouched for seven weeks.

## Next contribution being pursued

**List `kornsour/keda-inference-scaler` on Artifact Hub** as a `keda-scaler` package, which is
the mechanism the upstream project itself documents and actively surfaces (both in the
`external-scalers` README and on keda.sh/docs/latest/scalers/). This keeps the same scaler —
still a plausible, on-topic fit for KEDA's ecosystem — but resubmits it through the channel
KEDA's maintainers actually watch, instead of repeating a README-edit PR that already went
unreviewed once.

Listing on Artifact Hub requires registering the repo with an external service (adding
repository metadata and going through Artifact Hub's own review), which is a manual step
outside this repo — see the PR checklist for that follow-up. If that path stalls too, the
lighter fallback is a small docs or example contribution to `kedacore/keda` or `kserve/kserve`
(e.g. a scaler doc fix or a sample `ScaledObject`), which carries a shorter review path than
a new community-scaler listing.

## Why a standalone public repo (and not this one)

`kedacore/external-scalers` is a **community index, not a code monorepo** — every entry
links to a scaler hosted in its *own* repo (e.g. `balchua/artemis-ext-scaler`,
`devjoes/github-runner-autoscaler`). So the scaler needed its own dedicated, installable
home rather than living as a subdirectory of this capstone repo.

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

The goal is a genuine upstream contribution to a **CNCF** project in the exact domain of
this capstone, backed by working, tested, CI-built code — not a drive-by typo fix. #34
didn't land, so this is still open: once the Artifact Hub listing (or the fallback docs/sample
PR) is accepted, link it from the [write-up](WRITEUP.md).

## Remaining (manual)

1. Add Artifact Hub repository metadata to `kornsour/keda-inference-scaler` (an
   `artifacthub-repo.yml` plus a `keda-scaler`-kind package manifest) and register the repo
   on [artifacthub.io](https://artifacthub.io) — this is an external service and can't be
   done from this repo.
2. If Artifact Hub review stalls or rejects the listing, fall back to a small docs or
   example PR against `kedacore/keda` or `kserve/kserve` instead.
3. Once either lands, update this page and the `phase-2-capstone/README.md` checklist bullet
   with the merged link.
