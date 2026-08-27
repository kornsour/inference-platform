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
check_file "main_test.go" false
check_file "Dockerfile" false

if [ "$status" -ne 0 ]; then
  cat <<EOF

The vendored copy under phase-2-capstone/keda-inference-scaler/ has diverged
from the standalone repo (${UPSTREAM_REPO}). Port the change to both, or if
the drift is intentional (e.g. a deliberate temporary pin), update this
script's expectations alongside it.
EOF
  exit 1
fi

echo "OK: main.go, main_test.go, and Dockerfile match ${UPSTREAM_REPO}@${UPSTREAM_REF}"
