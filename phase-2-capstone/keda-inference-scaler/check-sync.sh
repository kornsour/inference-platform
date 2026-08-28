#!/usr/bin/env bash
# Fails if this vendored copy of the scaler has drifted from the standalone
# kornsour/keda-inference-scaler repo, beyond the expected module-path
# substitution in main.go. Run from this directory (phase-2-capstone/keda-inference-scaler).
#
# This keeps the capstone self-contained (no submodule / build-time fetch)
# while still catching silent divergence between the two copies. See
# https://github.com/kornsour/inference-platform/issues/13.
set -euo pipefail

UPSTREAM_REPO="kornsour/keda-inference-scaler"
UPSTREAM_REF="${UPSTREAM_REF:-main}"
UPSTREAM_MODULE="github.com/kornsour/keda-inference-scaler"
VENDOR_MODULE="github.com/kornsour/inference-platform/phase-2-capstone/keda-inference-scaler"
RAW_BASE="https://raw.githubusercontent.com/${UPSTREAM_REPO}/${UPSTREAM_REF}"

status=0

# check_file <path relative to this dir> <substitute module path?>
check_file() {
  local rel_path="$1" substitute="${2:-false}" tmp
  tmp="$(mktemp)"
  if ! curl -fsSL "${RAW_BASE}/${rel_path}" -o "$tmp"; then
    echo "::error::failed to fetch upstream ${UPSTREAM_REPO}@${UPSTREAM_REF}/${rel_path}"
    status=1
    rm -f "$tmp"
    return
  fi
  if [ "$substitute" = "true" ]; then
    sed "s#${UPSTREAM_MODULE}#${VENDOR_MODULE}#g" "$tmp" > "${tmp}.sub"
    mv "${tmp}.sub" "$tmp"
  fi
  if ! diff -u "$tmp" "$rel_path"; then
    echo "::error::${rel_path} has drifted from ${UPSTREAM_REPO}@${UPSTREAM_REF}/${rel_path}"
    status=1
  fi
  rm -f "$tmp"
}

check_file "main.go" true
# main_test.go now imports the split internal/* packages (see below), so it
# needs the same module-path substitution as main.go — it stopped being a
# plain, self-contained file the day upstream split main() apart.
check_file "main_test.go" true
check_file "Dockerfile" false

# Upstream split main() into internal/{config,metrics,observability,saturation}
# packages (kornsour/keda-inference-scaler#11). Vendored 1:1, same as main.go —
# every file here needs the same substitution, since these are same-module Go
# packages, not a separate dependency.
for f in \
  internal/config/config.go \
  internal/config/config_test.go \
  internal/metrics/cache.go \
  internal/metrics/cache_test.go \
  internal/metrics/metrics.go \
  internal/metrics/metrics_test.go \
  internal/observability/health.go \
  internal/observability/health_test.go \
  internal/observability/metrics.go \
  internal/observability/metrics_test.go \
  internal/observability/server.go \
  internal/observability/server_test.go \
  internal/saturation/saturation.go \
  internal/saturation/saturation_test.go \
; do
  check_file "$f" true
done

if [ "$status" -ne 0 ]; then
  cat <<EOF

The vendored copy under phase-2-capstone/keda-inference-scaler/ has diverged
from the standalone repo (${UPSTREAM_REPO}). Port the change to both (adding
any new internal/* file to the list in this script too), or if the drift is
intentional (e.g. a deliberate temporary pin), update this script's
expectations alongside it.
EOF
  exit 1
fi

echo "OK: main.go, main_test.go, Dockerfile, and internal/* match ${UPSTREAM_REPO}@${UPSTREAM_REF}"
