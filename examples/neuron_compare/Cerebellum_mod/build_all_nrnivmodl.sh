#!/usr/bin/env bash
# Run nrnivmodl in every directory under this tree that contains at least one .mod
# file (same workflow as: cd GoC/channel && nrnivmodl .).
#
# Usage:
#   ./build_all_nrnivmodl.sh
#   CLEAN=1 ./build_all_nrnivmodl.sh   # rm -rf x86_64 arm64 in each dir before build
#
# Requires NEURON on PATH (e.g. conda env with neuron / pip install neuron).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v nrnivmodl >/dev/null 2>&1; then
  echo "error: nrnivmodl not found in PATH. Install/activate NEURON first." >&2
  exit 1
fi

mapfile -t MOD_DIRS < <(find "$ROOT" -type f -name '*.mod' -printf '%h\n' | LC_ALL=C sort -u)

failed=()
for dir in "${MOD_DIRS[@]}"; do
  echo "========================================"
  echo "nrnivmodl in: $dir"
  echo "========================================"
  if [[ "${CLEAN:-0}" == 1 ]]; then
    rm -rf "$dir/x86_64" "$dir/arm64" "$dir/powerpc"
  fi
  if (cd "$dir" && nrnivmodl .); then
    :
  else
    failed+=("$dir")
  fi
done

if ((${#failed[@]})); then
  echo "error: nrnivmodl failed in ${#failed[@]} director(ies):" >&2
  printf '  %s\n' "${failed[@]}" >&2
  exit 1
fi

echo "ok: built ${#MOD_DIRS[@]} mechanism director(ies) under $ROOT"
