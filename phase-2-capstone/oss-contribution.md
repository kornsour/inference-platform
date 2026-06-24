# OSS contribution — prepared, ready to submit

The Phase 2 checklist calls for landing **one small PR to an OSS inference project**. The
work we built makes for a natural, low-risk contribution. This page is the **prepared
draft** — submitting it happens under *your* GitHub identity, so the final `git push` / PR
is yours to make. Verify the target's current state first (OSS repos move).

## Best-fit target: `kedacore/external-scalers`

KEDA maintains a community list of external scalers at
[github.com/kedacore/external-scalers](https://github.com/kedacore/external-scalers). The
[Go external scaler](keda-inference-scaler/README.md) we built — autoscaling LLM serving on
a composite KV-cache + queue-depth signal — is exactly the kind of community scaler that
list exists for. It's a one-line, well-scoped addition: low risk, clearly useful, and
directly tied to the capstone.

### The change

The README is a simple bulleted list (`- Name ([GitHub](url))`). Add one entry:

```diff
+ - LLM inference — vLLM KV-cache + request-queue saturation ([GitHub](https://github.com/kornsour/ai-inference/tree/main/phase-2-capstone/keda-inference-scaler))
```

### How to submit (your steps)

```bash
gh repo fork kedacore/external-scalers --clone
cd external-scalers
git checkout -b add-llm-inference-scaler
# add the bullet above to the community list in README.md
git commit -am "docs: add LLM-inference (vLLM KV-cache/queue) external scaler"
gh pr create --title "Add LLM-inference external scaler" \
  --body "Adds a community external scaler that autoscales vLLM on a composite KV-cache + queue-depth signal."
```

Before submitting: confirm the list doesn't already include it and that the bullet format
still matches the current README.

## Secondary candidate (if the above is taken)

A docs clarification to [`kedacore/keda-docs`](https://github.com/kedacore/keda-docs) — the
external-scalers guide documents the gRPC contract but has no end-to-end *inference*
example. A short worked example (KV-cache/queue → `inference-saturation`) modeled on our
scaler would fill a real gap. Same fork → branch → PR flow.

## Why this counts

It's a genuine upstream contribution to a **CNCF** project in the exact domain of the role,
backed by working code you can speak to in depth — not a drive-by typo fix. Link the merged
PR from the [write-up](WRITEUP.md) once it lands.
