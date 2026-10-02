#!/usr/bin/env bash
# Fetch every external input the analysis needs, at pinned revisions.
#
# Single entry point for a clean checkout. Delegates to the three
# per-source scripts so the pins live in exactly one place each; the
# checks below fail loudly if a delegated script drifts off the pin
# recorded here and in src/config.py.
#
# Disk: ~2.5 GB fetched, ~1.5 GB retained.
# Requires: `hf` (huggingface_hub[cli], see requirements.txt) and `git`.
# Nothing is compiled -- no Lean toolchain is installed or invoked.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Mirrors src/config.py. MATHLIB_COMMIT_FULL is the commit the published
# graph was built from (arXiv:2604.24797 reports it as 534cf0b).
MATHLIB_GRAPH_REVISION="8c706461fe266802197b62af324de12a3f1aa7fb"
GOEDEL_REVISION="b731852af8d8ab11498fda27bce9020738c01c59"
MATHLIB_COMMIT_FULL="534cf0b8f5267c3f20bf52f932ad5f9834187c35"

require_pin() {
  # require_pin <script> <expected-revision>
  local script="$1" pin="$2"
  if [[ ! -f "$script" ]]; then
    echo "FATAL: $script missing" >&2
    exit 2
  fi
  if ! grep -q "$pin" "$script"; then
    echo "FATAL: $script does not pin $pin" >&2
    echo "       Pins must agree across download_data.sh, the fetch" >&2
    echo "       script, and src/config.py. Reconcile before fetching." >&2
    exit 2
  fi
}

require_pin "$HERE/fetch_mathlib_graph.sh"   "$MATHLIB_GRAPH_REVISION"
require_pin "$HERE/fetch_machine_corpora.sh" "$GOEDEL_REVISION"
require_pin "$HERE/fetch_mathlib_source.sh"  "$MATHLIB_COMMIT_FULL"

echo "==> 1/3 mathlib dependency graph"
echo "        MathNetwork/MathlibGraph @ $MATHLIB_GRAPH_REVISION"
bash "$HERE/fetch_mathlib_graph.sh"

echo "==> 2/3 machine proof corpus"
echo "        Goedel-LM/Lean-workbook-proofs @ $GOEDEL_REVISION"
bash "$HERE/fetch_machine_corpora.sh"

echo "==> 3/3 mathlib4 source text"
echo "        leanprover-community/mathlib4 @ $MATHLIB_COMMIT_FULL"
bash "$HERE/fetch_mathlib_source.sh"

echo
echo "All three sources fetched at their pinned revisions."
echo "Next: make audit"
