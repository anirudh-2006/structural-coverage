#!/usr/bin/env bash
# Fetch mathlib4 SOURCE TEXT at the commit the published graph was built from.
#
# The graph dataset ships no statements and no proof bodies (mechanisms.ndjson
# is metadata, tactic_usage.ndjson is tactic name lists), so source-visible
# extraction needs the actual .lean files. Text only — no Lean toolchain, no
# build, nothing is compiled here.
#
# The paper reports commit 534cf0b; the 7-char form does not resolve via the
# GitHub API, so the full SHA is pinned instead. Committed 2026-02-02T21:52:49Z.
set -euo pipefail

DEST="$(dirname "$0")/../data/mathlib_src"
COMMIT="534cf0b8f5267c3f20bf52f932ad5f9834187c35"
REPO="https://github.com/leanprover-community/mathlib4.git"

if [ -d "$DEST/.git" ]; then
  echo "$DEST already exists; verifying pin"
else
  # Blob-filtered so history blobs are never fetched; only the trees and the
  # blobs reachable from this one commit are materialised.
  git clone --filter=blob:none --no-checkout "$REPO" "$DEST"
fi

git -C "$DEST" fetch --filter=blob:none origin "$COMMIT"
git -C "$DEST" checkout --detach "$COMMIT"

ACTUAL="$(git -C "$DEST" rev-parse HEAD)"
if [ "$ACTUAL" != "$COMMIT" ]; then
  echo "PIN MISMATCH: expected $COMMIT, got $ACTUAL" >&2
  exit 1
fi

echo "mathlib4 source at $ACTUAL"
echo "$(find "$DEST/Mathlib" -name '*.lean' | wc -l | tr -d ' ') .lean files under Mathlib/"
