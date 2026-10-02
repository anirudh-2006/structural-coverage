#!/usr/bin/env bash
# Machine-generated proof corpora. All pre-verified by their releasers.
set -euo pipefail

DEST="$(dirname "$0")/../data/machine_proofs"
mkdir -p "$DEST"

# Start with Goedel only. Do not fetch the rest until the audit passes.
hf download Goedel-LM/Lean-workbook-proofs \
  --repo-type dataset \
  --revision b731852af8d8ab11498fda27bce9020738c01c59 \
  --local-dir "$DEST/goedel_lean_workbook"

echo "Fetched Goedel Lean Workbook proofs (~29.7K)."
echo "DeepSeek + Goedel-V2 deliberately not fetched — gate on the audit first."
