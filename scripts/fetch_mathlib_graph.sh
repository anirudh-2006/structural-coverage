#!/usr/bin/env bash
# Fetch the published mathlib dependency graph.
# Source: arXiv:2604.24797 (Li, Peng, Severini, Shafto).
# We do NOT rebuild this. See CLAUDE.md §4.
set -euo pipefail

DEST="$(dirname "$0")/../data/mathlib_graph"
REVISION="8c706461fe266802197b62af324de12a3f1aa7fb"
mkdir -p "$DEST"

# Selective by design. The repo is 2.3GB and ships TWO edge files with
# identical headers:
#   edges.csv        753MB  full Lean environment, 10.9M edges, 633,364 nodes
#   mathlib_edges.csv 584MB mathlib-scoped, 8,436,366 edges  <- the paper's graph
# Only the second matches arXiv:2604.24797's counts. We do not download the
# first, so it cannot be loaded by mistake.
# Filenames are POSITIONAL in the `hf` CLI. Passing them after --include
# makes the first one the pattern value and silently drops the rest
# ("Ignoring --include since filenames have been explicitly set").
hf download MathNetwork/MathlibGraph \
  "mathlib_edges.csv" \
  "v2/declaration/nodes.csv" \
  "v2/declaration/metrics.csv" \
  "v2/summary.json" \
  "tactic_usage.ndjson" \
  "README.md" \
  --repo-type dataset \
  --revision "$REVISION" \
  --local-dir "$DEST"

echo "Fetched to $DEST at revision $REVISION"
